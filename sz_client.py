"""ShowZ Store / GundamIT 后台 Playwright 客户端（有头模式）。

职责：
1. 登录态持久化 storage_state，首次登录，后续复用
2. 打开新品添加页并填充 18 个基础字段（对齐油猴脚本 fillInFields）
3. 主图走 Playwright iframe 真实上传（#PicUpload_0 → set_input_files → #button_add）
4. listing 图走 HTTP editor 端点（带 Playwright cookies），拿回 URL 拼进 CKEditor 描述 HTML
5. 切换到属性 tab，调 DeepSeek 做 AI 属性匹配；Availability 走纯规则
6. 填充完成后停在保存按钮前，用户手动核对并保存

site="sz"|"gd"：切换登录 URL、加载对应 logo（由 image_processor 处理）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from playwright.sync_api import Frame, Page, sync_playwright, TimeoutError as PWTimeout

from ai_matcher import (
    AI_ATTRIBUTE_CONFIGS,
    LABEL_ALIASES,
    call_deepseek,
    decide_availability,
)
from image_processor import ImageBundle, ProcessedListing, ProcessedMain

logger = logging.getLogger(__name__)

AI_ATTRIBUTES = [
    "Theme",
    "Hot Categories",
    "Product Type",
    "Company",
    "Character",
    "Featured In",
    "Size",
    "Scale",
]


@dataclass
class SzConfig:
    site: str  # "sz" | "gd"
    login_url: str
    add_product_url: str
    username: str
    password: str
    deepseek_api_key: str
    storage_state_path: Path

    @property
    def base_url(self) -> str:
        """从 add_product_url 提取 `https://host/manage/`。"""
        p = urlparse(self.add_product_url)
        return f"{p.scheme}://{p.netloc}/manage/"

    @property
    def upload_endpoint(self) -> str:
        return self.base_url + "?do_action=action.file_upload_plugin&size=editor"


class SzClientError(Exception):
    """SZ 客户端操作失败时抛出。"""


class SzClient:
    def __init__(self, config: SzConfig, headless: bool = False):
        self.config = config
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self.page: Optional[Page] = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--start-maximized"],
        )
        storage = (
            str(self.config.storage_state_path)
            if self.config.storage_state_path.exists()
            else None
        )
        self._context = self._browser.new_context(
            storage_state=storage,
            no_viewport=True,
        )
        self.page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._context is not None:
            try:
                self.config.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                self._context.storage_state(path=str(self.config.storage_state_path))
            except Exception as e:
                logger.warning("保存登录态失败: %s", e)
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright is not None:
            self._playwright.stop()

    # ---------- 登录 ----------

    def ensure_logged_in(self) -> None:
        """确保已登录。session 失效则走账密登录。goto 超时 60s + 一次重试。"""
        assert self.page is not None
        self._goto_with_retry(self.config.add_product_url)
        if self._is_login_page():
            logger.info("检测到未登录，执行账号密码登录")
            self._perform_login()
            self._goto_with_retry(self.config.add_product_url)
        if self._is_login_page():
            raise SzClientError("登录失败，仍停留在登录页")

    def _goto_with_retry(self, url: str, timeout: int = 60000) -> None:
        """带一次重试的 goto，超时 60s。"""
        assert self.page is not None
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except PWTimeout:
            logger.warning("页面加载超时（%ds），重试一次", timeout // 1000)
            self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)

    def _is_login_page(self) -> bool:
        assert self.page is not None
        try:
            return self.page.locator("input[type='password']").count() > 0
        except Exception:
            return False

    def _perform_login(self) -> None:
        assert self.page is not None
        self._goto_with_retry(self.config.login_url)
        user_sel = self._find_first(
            [
                "input[name='UserName']",
                "input[name='username']",
                "input[type='text']",
            ]
        )
        pwd_sel = self._find_first(
            ["input[name='Password']", "input[name='password']", "input[type='password']"]
        )
        if user_sel is None or pwd_sel is None:
            raise SzClientError("登录页未找到用户名/密码输入框")
        user_sel.fill(self.config.username)
        pwd_sel.fill(self.config.password)
        pwd_sel.press("Enter")
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass

    def _find_first(self, selectors):
        assert self.page is not None
        for sel in selectors:
            loc = self.page.locator(sel)
            if loc.count() > 0:
                return loc.first
        return None

    # ---------- 填充 ----------

    def fill_product(
        self,
        data: Dict[str, str],
        image_bundle: Optional[ImageBundle] = None,
    ) -> None:
        """填充 SZ 新品添加页基础字段 + 图片上传 + AI 属性。

        流程：基础字段 → 主图（iframe）→ listing 图（HTTP）→ 描述 HTML（拼 listing img）→ AI 属性
        image_bundle=None 时退化成旧行为：跳过图片，描述只填文本。
        """
        assert self.page is not None
        page = self.page

        # 等待页面核心字段渲染
        try:
            page.wait_for_selector("input[name='Name_en']", timeout=20000)
        except PWTimeout as e:
            raise SzClientError("产品添加页未加载出预期字段（Name_en）") from e

        # 分类（需要点左侧 dd a 列表）
        category = (data.get("category") or "").strip()
        if category:
            self._select_category(category)

        # 基础字段
        self._fill_by_name("Name_en", data.get("product_title", ""))
        self._fill_by_name("Number", data.get("number", ""))
        self._fill_by_name("SearchKeyword", data.get("search_keyword", ""))
        self._fill_by_name("PageUrl", data.get("page_url", ""))

        # SEO 标题按站点加后缀
        seo_title = (data.get("product_title") or "").strip()
        url_lower = page.url.lower()
        if "showzstore.com" in url_lower:
            seo_title += " - Show.Z Store"
        elif "gundamit.com" in url_lower:
            seo_title += " - GunDamit Store"
        elif "gkloot.com" in url_lower:
            seo_title += " | GKLoot.com"
        self._fill_by_name("SeoTitle_en", seo_title)

        self._fill_by_name("SeoKeyword_en", data.get("seo_keyword_en", ""))
        self._fill_by_name("SeoDescription_en", data.get("seo_description_en", ""))

        # 图片上传 + 描述 HTML 合成（如果提供了 bundle）
        listing_urls: List[str] = []
        if image_bundle is not None:
            if image_bundle.main is not None:
                self._upload_main_image(image_bundle.main)
            if image_bundle.listings:
                listing_urls = self._upload_listings_http(image_bundle.listings)

        # 描述（CKEditor）：文本 + listing 图 HTML
        description_html = self._compose_description(
            data.get("description_en") or "",
            data.get("product_title") or "",
            listing_urls,
        )
        self._set_ckeditor_raw("Description_en", description_html)

        # 价格/库存
        self._fill_by_name("Price_1", data.get("price") or "0")
        self._fill_by_name("Stock", data.get("stock") or "20")

        # 复选框
        self._set_checkbox("IsComing", data.get("is_coming") == "打开")
        presale_price = (data.get("presale_price") or "").strip()
        if presale_price:
            self._set_checkbox("IsPresale", True)
            self._fill_by_name("PresalePrice", presale_price)
        else:
            self._set_checkbox("IsPresale", False)
        self._set_checkbox("PreDiscount", data.get("pre_discount") == "打开")
        self._set_checkbox("IsBatteries", data.get("is_batteries") == "打开")

        # 尺寸 / 重量
        self._fill_by_name("Cubage[0]", data.get("length", ""))
        self._fill_by_name("Cubage[1]", data.get("width", ""))
        self._fill_by_name("Cubage[2]", data.get("height", ""))
        self._fill_by_name("Weight", data.get("weight", ""))

        # 切换到属性 tab 并做 AI 匹配
        self._handle_attributes(data)

    # ---------- 填充辅助 ----------

    def _fill_by_name(self, name: str, value: str) -> None:
        assert self.page is not None
        safe = value if value is not None else ""
        result = self.page.evaluate(
            """
            ({name, value}) => {
                const el = document.getElementsByName(name)[0];
                if (!el) return {ok: false};
                el.value = value;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return {ok: true};
            }
            """,
            {"name": name, "value": str(safe)},
        )
        if not result.get("ok"):
            logger.warning("未找到字段: name=%s", name)

    def _set_checkbox(self, name: str, checked: bool) -> None:
        assert self.page is not None
        self.page.evaluate(
            """
            ({name, checked}) => {
                const el = document.getElementsByName(name)[0];
                if (!el) return;
                if (el.checked !== checked) el.click();
            }
            """,
            {"name": name, "checked": checked},
        )

    def _compose_description(
        self, description_text: str, product_title: str, listing_urls: List[str]
    ) -> str:
        """把纯英文描述 + listing 图 URL 拼成最终要塞进 CKEditor 的 HTML（对齐油猴脚本 v2.1.0）。"""
        body_html = (description_text or "").replace("\n", "<br>")
        wrapped = (
            f'<span style="line-height:250%;"><span style="font-size:24px;">'
            f'<span style="font-family:karla;">{body_html}</span></span></span>'
        )
        for i, url in enumerate(listing_urls):
            alt = f"{product_title} - View {i + 1}" if product_title else ""
            img_attr = f' alt="{alt}" title="{alt}"' if alt else ""
            wrapped += f'<br /><br /><img src="{url}"{img_attr} />'
        return wrapped

    def _set_ckeditor_raw(self, instance_name: str, full_html: str) -> None:
        """直接把已拼好的 HTML 塞进 CKEditor（不再做 wrap）。"""
        assert self.page is not None
        ok = self.page.evaluate(
            """
            ({name, content}) => {
                if (window.CKEDITOR && CKEDITOR.instances[name]) {
                    CKEDITOR.instances[name].setData(content);
                    return true;
                }
                return false;
            }
            """,
            {"name": instance_name, "content": full_html},
        )
        if not ok:
            logger.warning("CKEDITOR 实例未就绪：%s", instance_name)

    def _set_ckeditor(self, instance_name: str, html_body: str) -> None:
        """通过 CKEDITOR 实例 API 设置描述内容，格式对齐油猴脚本。"""
        assert self.page is not None
        body_html = (html_body or "").replace("\n", "<br>")
        wrapped = (
            f'<span style="line-height:250%;"><span style="font-size:24px;">'
            f'<span style="font-family:karla;">{body_html}</span></span></span>'
        )
        ok = self.page.evaluate(
            """
            ({name, content}) => {
                if (window.CKEDITOR && CKEDITOR.instances[name]) {
                    CKEDITOR.instances[name].setData(content);
                    return true;
                }
                return false;
            }
            """,
            {"name": instance_name, "content": wrapped},
        )
        if not ok:
            logger.warning("CKEDITOR 实例未就绪：%s", instance_name)

    def _select_category(self, category_name: str) -> None:
        """在左侧分类列表里点击匹配的项（dd a）。"""
        assert self.page is not None
        clicked = self.page.evaluate(
            """
            (name) => {
                const links = document.querySelectorAll('dd a');
                for (const link of links) {
                    if (link.textContent && link.textContent.includes(name)) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }
            """,
            category_name,
        )
        if not clicked:
            logger.warning("未找到分类: %s", category_name)

    # ---------- AI 属性 ----------

    def _handle_attributes(self, data: Dict[str, str]) -> None:
        assert self.page is not None
        page = self.page

        # 切换到属性 tab
        try:
            attr_link = page.locator("a[data-name='attrbute_info']").first
            if attr_link.count() == 0:
                logger.warning("未找到属性 tab 切换链接，跳过 AI 属性")
                return
            attr_link.click()
            page.wait_for_timeout(1200)
        except Exception as e:
            logger.warning("切换属性 tab 失败: %s", e)
            return

        # Availability（纯规则）
        availability = decide_availability(data)
        self._click_choice_in_container("Availability", availability)
        logger.info("Availability = %s", availability)

        # AI 属性逐个处理
        for attr_name in AI_ATTRIBUTES:
            config = AI_ATTRIBUTE_CONFIGS.get(attr_name)
            if not config:
                continue

            # 检查输入是否非空
            has_input = any(
                (data.get(f["key"]) or "").strip() for f in config["inputFields"]
            )
            if not has_input:
                logger.info("%s: 输入字段全空，跳过", attr_name)
                continue

            options = self._read_container_options(attr_name)
            if not options:
                logger.info("%s: 未找到容器或无可选项（跳过）", attr_name)
                continue

            logger.info("%s 可选项 %d 个", attr_name, len(options))
            try:
                suggested = call_deepseek(
                    self.config.deepseek_api_key, config, data, options
                )
                logger.info("%s AI 建议: %s", attr_name, suggested)
                self._click_choice_in_container(
                    attr_name, suggested, fallback=config.get("defaultValue")
                )
            except Exception as e:
                logger.error("%s AI 匹配失败: %s", attr_name, e)
                fallback = config.get("defaultValue")
                if fallback:
                    self._click_choice_in_container(attr_name, fallback)

    def _read_container_options(self, attr_name: str):
        """读取指定属性容器下所有 .choice_btn 的选项文本（首行）。"""
        assert self.page is not None
        aliases = LABEL_ALIASES.get(attr_name, [attr_name])
        return self.page.evaluate(
            """
            (aliases) => {
                const labels = document.querySelectorAll('div.rows label');
                let container = null;
                for (const alias of aliases) {
                    for (const lb of labels) {
                        if (lb.textContent && lb.textContent.includes(alias)) {
                            container = lb.closest('div.rows');
                            break;
                        }
                    }
                    if (container) break;
                }
                if (!container) return [];
                const btns = container.querySelectorAll('.choice_btn');
                return Array.from(btns).map(b => b.textContent.trim().split('\\n')[0].trim());
            }
            """,
            aliases,
        )

    def _click_choice_in_container(
        self, attr_name: str, target_text: str, fallback: Optional[str] = None
    ) -> None:
        """在指定属性容器内点击与 target_text 匹配的选项；失败则用 fallback。"""
        assert self.page is not None
        aliases = LABEL_ALIASES.get(attr_name, [attr_name])
        result = self.page.evaluate(
            """
            ({aliases, target, fallback}) => {
                const labels = document.querySelectorAll('div.rows label');
                let container = null;
                for (const alias of aliases) {
                    for (const lb of labels) {
                        if (lb.textContent && lb.textContent.includes(alias)) {
                            container = lb.closest('div.rows');
                            break;
                        }
                    }
                    if (container) break;
                }
                if (!container) return {ok: false, reason: 'no_container'};

                const btns = Array.from(container.querySelectorAll('.choice_btn'));
                // 先取消所有已选
                for (const btn of btns) {
                    const cb = btn.querySelector('input[type="checkbox"]');
                    if (cb && cb.checked) cb.click();
                }

                const pickByText = (text) => {
                    if (!text) return null;
                    // 精确
                    for (const btn of btns) {
                        const t = btn.textContent.trim().split('\\n')[0].trim();
                        if (t === text) return btn;
                    }
                    // 大小写模糊
                    for (const btn of btns) {
                        const t = btn.textContent.trim().split('\\n')[0].trim();
                        if (t.toLowerCase() === text.toLowerCase()) return btn;
                    }
                    return null;
                };

                let picked = pickByText(target);
                let usedFallback = false;
                if (!picked && fallback) {
                    picked = pickByText(fallback);
                    usedFallback = true;
                }
                if (!picked) return {ok: false, reason: 'no_match'};

                const cb = picked.querySelector('input[type="checkbox"]');
                if (cb) cb.click();
                return {
                    ok: true,
                    text: picked.textContent.trim().split('\\n')[0].trim(),
                    usedFallback,
                };
            }
            """,
            {"aliases": aliases, "target": target_text, "fallback": fallback},
        )
        if result.get("ok"):
            tag = "fallback" if result.get("usedFallback") else "match"
            logger.info("%s → %s (%s)", attr_name, result.get("text"), tag)
        else:
            logger.warning("%s 选项未命中: %s", attr_name, result.get("reason"))

    # ---------- 图片上传 ----------

    def _upload_main_image(self, main: ProcessedMain) -> None:
        """主图上传：点 #PicUpload_0 → 定位 photo choice iframe → set_input_files → #button_add 提交。

        iframe URL 模式：`?m=set&a=photo&d=choice&obj=PicUpload_0&...&iframe=1&...`
        描述图 iframe 的标记是 `save=_Detail`，通过精确 URL 匹配 obj=PicUpload_0 过滤。
        """
        assert self.page is not None
        page = self.page

        btn = page.locator("#PicUpload_0")
        if btn.count() == 0:
            raise SzClientError("未找到主图上传按钮 #PicUpload_0")

        logger.info("主图上传：点击 #PicUpload_0")
        btn.first.click()
        page.wait_for_timeout(1500)  # 等 iframe 挂载

        target_frame = self._find_photo_choice_iframe("PicUpload_0", timeout_ms=10000)
        if target_frame is None:
            logger.error(
                "主图 iframe 未找到。当前所有 frames: %s",
                [(f.url or "(empty)") for f in page.frames],
            )
            raise SzClientError("主图上传 iframe 未出现")
        logger.info("主图 iframe: %s", target_frame.url)

        # 等 iframe 加载 + JS 初始化（jQuery file_upload 插件依赖）
        try:
            target_frame.wait_for_load_state("load", timeout=30000)
        except PWTimeout:
            logger.warning("iframe load 超时，继续尝试")
        page.wait_for_timeout(1500)

        # 找 file input。SZ 的"本地上传"走 jQuery file_upload 插件 —
        # set_input_files 触发 change → XHR 上传 → iframe 自动关闭 → 主页面 PicPath[] 被回填
        # 全程不需要手动点 #button_add（#button_add 只在"选择已有图库"分支用到）
        file_loc = target_frame.locator("input[type='file']")
        if file_loc.count() == 0:
            raise SzClientError("主图 iframe 内未找到 file input")
        file_loc.first.set_input_files(str(main.path))
        logger.info("主图文件已注入: %s（等 XHR 上传 + iframe 自动关 + PicPath[] 回填）", main.name)

        # 等 PicPath[] 被回填（最多 30s，大图慢网络场景兜底）
        try:
            page.wait_for_function(
                """() => {
                    const el = document.querySelector("input[name='PicPath[]']");
                    return el && el.value && el.value.length > 0;
                }""",
                timeout=30000,
            )
            pic_val = page.evaluate(
                "() => document.querySelector(\"input[name='PicPath[]']\").value"
            )
            logger.info("主图 PicPath[] 回填: %s", pic_val)
        except PWTimeout:
            logger.warning("等待 PicPath[] 回填超时（30s），主图可能未上传成功")
            self._dismiss_photo_popup()

    def _dismiss_photo_popup(self) -> None:
        """主图上传弹窗超时未关时，主动关掉弹窗 + 背景遮罩，避免拦截后续所有点击。"""
        assert self.page is not None
        dismissed = self.page.evaluate(
            """() => {
                let closed = false;
                const popup = document.querySelector('.pop_form.photo_choice');
                if (popup && popup.style.display !== 'none') {
                    popup.style.display = 'none';
                    closed = true;
                }
                const mask = document.getElementById('div_mask');
                if (mask && mask.style.display !== 'none') {
                    mask.style.display = 'none';
                    closed = true;
                }
                return closed;
            }"""
        )
        if dismissed:
            logger.info("主图弹窗 + 遮罩已手动关闭（避免遮挡后续操作）")

    def _find_photo_choice_iframe(
        self, obj: str, timeout_ms: int = 10000
    ) -> Optional[Frame]:
        """按 URL 模式定位图片上传 iframe：`d=choice&obj=<obj>&iframe=1` 且不含 save=_Detail。"""
        assert self.page is not None
        page = self.page
        step = 300
        elapsed = 0
        while elapsed < timeout_ms:
            for f in page.frames:
                if f == page.main_frame:
                    continue
                url = f.url or ""
                if "d=choice" not in url or "iframe=1" not in url:
                    continue
                if f"obj={obj}" not in url:
                    continue
                if "save=_Detail" in url or "save=_detail" in url:
                    continue
                return f
            page.wait_for_timeout(step)
            elapsed += step
        return None

    def _upload_listings_http(self, listings: List[ProcessedListing]) -> List[str]:
        """listing 图走 HTTP editor 端点上传，从 Playwright context 取 cookies 鉴权。

        返回 CDN URL 列表（顺序与 listings 一致）。失败的项会跳过并 warn。
        """
        if not listings:
            return []

        req_session = self._build_requests_session()
        endpoint = self.config.upload_endpoint
        urls: List[str] = []
        for idx, li in enumerate(listings, 1):
            try:
                resp = req_session.post(
                    endpoint,
                    files={"Filedata": (li.name, li.data, "image/jpeg")},
                    headers={"x-requested-with": "XMLHttpRequest"},
                    timeout=30,
                )
                resp.raise_for_status()
                j = resp.json()
                url = j.get("files", [{}])[0].get("url")
                if not url:
                    logger.warning("listing %d/%d 上传返回无 url: %s", idx, len(listings), j)
                    continue
                urls.append(url)
                logger.info(
                    "listing %d/%d %s → %s", idx, len(listings), li.name, url
                )
            except Exception as e:
                logger.error(
                    "listing %d/%d %s 上传失败: %s", idx, len(listings), li.name, e
                )
        return urls

    def _build_requests_session(self) -> requests.Session:
        """从 Playwright context 导出 cookie，构造一个能直接调 SZ 后台 API 的 requests.Session。"""
        assert self._context is not None
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0"})
        for c in self._context.cookies():
            sess.cookies.set(
                c.get("name"),
                c.get("value"),
                domain=c.get("domain", ""),
                path=c.get("path", "/"),
            )
        return sess

    # ---------- 暂停等待 ----------

    def pause_for_manual_save(self) -> None:
        """停在保存按钮前，等用户人工核对并保存。关窗后脚本自动退出。"""
        assert self.page is not None
        print("\n" + "=" * 60)
        print("✅ 字段填充完成。请在浏览器中核对后手动点击【保存】按钮。")
        print("完成后直接关闭浏览器窗口/tab，脚本会自动退出。")
        print("=" * 60, flush=True)
        try:
            while not self.page.is_closed():
                self.page.wait_for_timeout(1000)
        except Exception:
            pass
