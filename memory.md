# 网站自动上传文案

## 项目概述

电商后台新品上架引擎，两个通道并存：

- **Python + Playwright 有头通道**（v3.0.0 推荐）：打开 Chromium 自动填字段，停在保存按钮前等人工核对（对齐 ERP 自动上传文案的交互模型）
- **油猴脚本通道**（v2.1.0 备用）：Tampermonkey 浏览器端，SZ/GD/GKLoot 三站通用

## 核心文件

| 文件 | 说明 |
|------|------|
| `sz_upload.py` | CLI 入口，v3.1.0，`--site sz\|gd` 切换站点 |
| `sz_client.py` | Playwright 封装：session / 登录 / 字段填充 / 主图 iframe 上传 / listing HTTP 上传 / AI 属性 |
| `image_processor.py` | PIL 图片处理 + 桌面目录启发式搜索（v3.1.0 新增） |
| `ai_matcher.py` | DeepSeek API 客户端 + 8 类 AI 属性配置 |
| `parser.py` | 多产品 .docx 解析，按 SKU 定位列号 |
| `自动上传文案.user.js` | 油猴脚本 v2.1.0 |
| `.env` / `.env.example` | SZ/GD 凭据 + URL + DeepSeek Key |
| `requirements.txt` | python-docx / playwright / Pillow / requests / python-dotenv |
| `session/sz_storage.json` / `session/gd_storage.json` | 按站点分文件持久化登录态 |

## Playwright 流程（v3.1.0）

```
python3 sz_upload.py <SKU> [--site sz|gd]
       ↓
load .env (按 prefix) → parse .docx (18 字段) → image_processor.build_bundle(sku, site)
       ↓
build_bundle: 桌面搜 *<SKU>*/ → 选图片子目录（优先「原图」）
              → PIL 主图 500² 居中+水印 → 临时文件
              → PIL listing 850w+水印 → 字节列表
       ↓
启动 Chromium 有头 → 加载 session/{site}_storage.json → 打开添加页（按 site 的 ADD_PRODUCT_URL）
       ↓
填充基础字段：分类 → Name_en → Number → SearchKeyword → PageUrl
              → SEO 标题（按 URL 加站点后缀）→ SeoKeyword → SeoDescription
       ↓
主图上传：点 #PicUpload_0 → 找 d=choice&obj=PicUpload_0&iframe=1 的 iframe
         → set_input_files（jQuery file_upload 插件自动 XHR 上传 + iframe 自动关）
         → wait_for_function PicPath[] 非空
       ↓
listing 上传：Playwright context.cookies() → requests.Session
             → 并发 POST 到 base_url?do_action=action.file_upload_plugin&size=editor
             → 拿 CDN URL 列表
       ↓
描述合成：描述文本 wrapped 成 SZ 富文本 span + 每张 listing 拼 <br/><br/><img ... /> → CKEditor.setData
       ↓
继续基础字段：Price_1 / Stock / IsComing / IsPresale+PresalePrice / PreDiscount
              / IsBatteries / Cubage[0..2] / Weight
       ↓
属性 tab：a[data-name='attrbute_info'] → Availability 规则 + 8 个 AI 属性 DeepSeek 逐个匹配
       ↓
停在保存按钮前 → 用户核对保存 → 关窗退出
```

## 字段映射（parser.py FIELD_ROW_MAPPING）

.docx 第一个表格，第 3 行定位列号（SKU 匹配），18 行字段读取：

| 行 | 字段 | 行 | 字段 |
|---|---|---|---|
| 1 | product_title | 17 | stock |
| 2 | category | 18 | is_coming |
| 3 | number (SKU) | 19 | presale_price |
| 4 | search_keyword | 20 | pre_discount |
| 5 | page_url | 21 | length |
| 6 | description_en | 22 | width |
| 11 | seo_keyword_en | 23 | height |
| 12 | seo_description_en | 24 | weight |
| 14 | price | 29 | is_batteries |

## SZ 后台字段名映射（sz_client.py）

通过 `document.getElementsByName(...)` 定位（与油猴脚本一致）：
- Name_en / Number / SearchKeyword / PageUrl
- SeoTitle_en / SeoKeyword_en / SeoDescription_en
- Description_en（走 CKEDITOR.instances['Description_en'].setData）
- Price_1 / Stock / IsComing / IsPresale / PresalePrice / PreDiscount / IsBatteries
- Cubage[0..2] / Weight
- 分类点击 `dd a` 文本匹配
- 属性 tab 切换 `a[data-name='attrbute_info']`
- AI 属性容器：`div.rows label` 含别名 → 最近的 `div.rows` → `.choice_btn` 列表

## AI 属性（ai_matcher.py）

与油猴脚本 AI_ATTRIBUTE_CONFIGS 一致：
- **Availability**（纯规则）：有预售价 → Pre-Order；Coming soon=打开 → Coming Soon；stock ≤ 0 → Sold Out；否则 In Stock
- **Theme / Hot Categories / Product Type / Company / Character / Featured In / Size / Scale**：调 DeepSeek，system + user prompt 照搬油猴脚本，temperature 0.01

## 首次使用

1. `cp .env.example .env` 填写 SZ_USERNAME / SZ_PASSWORD / DEEPSEEK_API_KEY
2. `pip3 install -r requirements.txt`
3. `python3 -m playwright install chromium`
4. `python3 sz_upload.py <SKU>` 跑一次，首次会自动登录并保存 session

## 用法

```bash
python3 sz_upload.py MS-B04A-TEST                               # 桌面搜
python3 sz_upload.py "/path/to/文案.docx" MS-B04A-TEST           # 显式路径
python3 sz_upload.py MS-B04A-TEST --headless                    # 无头调试
```

## Claude Code Skill

`~/.claude/skills/website-upload/SKILL.md` — 对话中说「给 XXX 上架到 SZ」自动触发。

## 支持网站

- ShowzStore (`showzstore.com`) — Python Playwright + 油猴双通道
- GundamIT (`gundamit.com`) — 仅油猴
- GKLoot (`gkloot.com`) — 仅油猴

## 当前版本

v3.1.0 — 图片上传 + GD 通道上线。主图走 Playwright iframe 真实上传（本地上传分支自动完成），listing 图走 HTTP editor 端点并拼进 CKEditor 描述。`--site sz|gd` 切换站点。

## 关键约束

- **绝不代点保存按钮**，必须由用户在浏览器里人工核对后手动点
- **绝不调用任何 SZ 删除 API**（2026-04-09 误删事件教训）
- DeepSeek Key 走 `.env`（油猴脚本的硬编码是遗留 TODO）
- 登录失败不要盲目重试，立即报告

## v3.1.0 技术笔记（2026-04-14 实测得到的关键事实）

**主图 iframe 的真实机制**：
- URL 模式：`?m=set&a=photo&d=choice&obj=PicUpload_<N>&save=&id=PicDetail%20.img[num;<N>]&type=products&maxpic=10&iframe=1&r=<random>`
- 描述图 iframe 与主图共用同一个 URL 模式，差别在 `save` 参数（描述图有 `save=_Detail`）
- iframe body 用 jQuery file_upload 插件，有两个分支：
  1. **本地上传** — set_input_files 触发 change 事件 → jQuery 插件自动 XHR 上传 → iframe 自动关闭 → 主页 PicPath[] 被回填。全程**不需要**点 `#button_add`
  2. **选择已有图库** — 用户勾选库里的图后，点 `#button_add` 提交选中 PId[]
- Playwright 走分支 1，全自动无需任何按钮点击

**listing 图 HTTP 上传端点**：
- `{base_url}?do_action=action.file_upload_plugin&size=editor`
- FormData field: `Filedata`
- 返回 `{"files":[{"url":"/u_file/..."}]}`，拿 url 即可
- 从 Playwright context 导出 cookies 后，requests.Session 直接调用即可成功（SZ/GD 通用）

**CKEditor 描述 HTML 合成**：
- 油猴脚本 v2.1.0 和新品上架链 sz_listing.py 都用同一个 wrapping：`<span style="line-height:250%;"><span style="font-size:24px;"><span style="font-family:karla;">{body}</span></span></span>`
- listing 图拼接格式：`<br /><br /><img src="{url}" alt="{title} - View {N}" title="{title} - View {N}" />`
- CKEditor API: `CKEDITOR.instances['Description_en'].setData(fullHtml)` 一次性塞入

**踩过的坑**：
- 最开始用"找 #button_add"启发式定位主图 iframe — 失败。SZ 主页面上本身就有 #button_add 元素，误命中；而 iframe 里在本地上传分支根本不渲染 #button_add
- 网页 iframe body 里装了大量 jQuery 依赖 script，networkidle 不一定可靠；最终用 `wait_for_load_state("load")` + 固定 1.5s 缓冲足够
- 0.PNG 大写扩展名要在 glob 里显式枚举大小写，否则 Linux/macOS 区分大小写时会漏

## 已知安全问题

- `自动上传文案.user.js:156` 硬编码 DeepSeek API Key（`sk-240445142ba34cfcb03c55c6938ef67b`），违反红线第 1 条，需要轮换并迁移到用户配置存储

## 相关项目

- **新品上架链**：流水线编排，保留独立的无头 HTTP 版 `sz_listing.py` 用于后台跑
- **网站图片上传**：可共享 logos/（Playwright 版目前不处理图片，由用户手动在浏览器里传）
- **暗源新品自动化**：上游生成 .docx 文案
- **ERP自动上传文案**：同一交互模型（Playwright 有头 + 停在保存按钮前），参考实现
