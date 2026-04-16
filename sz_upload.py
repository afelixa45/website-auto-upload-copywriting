"""网站自动上传文案 — SZ / GD 有头 Playwright 入口（v3.1.0）。

用法：
    python sz_upload.py <SKU>                           # SZ，桌面搜文件夹
    python sz_upload.py <.docx 绝对路径> <SKU>           # SZ，显式指定 docx
    python sz_upload.py --site gd <SKU>                  # GD 站点
    python sz_upload.py --site sz <SKU> --no-images      # 跳过图片，只填文本
    python sz_upload.py <SKU> --headless                 # 无头模式（默认有头）

流程：
    1. 读取 .env 获取站点凭据 + DeepSeek Key
    2. 解析 .docx → 18 字段
    3. 桌面搜 SKU 文件夹 → 处理主图 500²+水印 / listing 850w+水印
    4. 启动 Chromium 有头 → 加载 session 或自动登录
    5. 填充基础字段
    6. 主图：点 #PicUpload_0 → 定位主图 iframe → set_input_files → #button_add 提交
    7. listing 图：走 HTTP editor 端点并发上传（复用 Playwright cookies）
    8. 描述：纯英文文本 + listing 图 HTML 一起塞进 CKEditor
    9. 切属性 tab → Availability 规则 + 8 类 DeepSeek AI 匹配
    10. 停在保存按钮前，用户人工核对并保存，关窗退出
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from image_processor import ImageBundle, build_bundle
from parser import DocxParseError, parse_docx
from sz_client import SzClient, SzClientError, SzConfig


VERSION = "3.1.0"
PROJECT_DIR = Path(__file__).resolve().parent
LOG_DIR = PROJECT_DIR / "logs"
SESSION_DIR = PROJECT_DIR / "session"
ENV_PATH = PROJECT_DIR / ".env"
DESKTOP = Path.home() / "Desktop"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"sz_upload_{datetime.now().strftime('%Y-%m-%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format=f"[%(asctime)s] | v{VERSION} | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_config(site: str) -> SzConfig:
    """按站点前缀（SZ/GD）从 .env 加载配置。"""
    if not ENV_PATH.exists():
        raise SystemExit(
            f"未找到 .env 文件: {ENV_PATH}\n"
            f"请复制 .env.example 为 .env 并填写站点凭据 + DeepSeek API Key。"
        )
    load_dotenv(ENV_PATH)
    prefix = site.upper()  # "SZ" or "GD"
    login_url = os.getenv(f"{prefix}_LOGIN_URL", "").strip()
    add_url = os.getenv(f"{prefix}_ADD_PRODUCT_URL", "").strip()
    username = os.getenv(f"{prefix}_USERNAME", "").strip()
    password = os.getenv(f"{prefix}_PASSWORD", "").strip()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    missing = [
        name
        for name, value in [
            (f"{prefix}_LOGIN_URL", login_url),
            (f"{prefix}_ADD_PRODUCT_URL", add_url),
            (f"{prefix}_USERNAME", username),
            (f"{prefix}_PASSWORD", password),
            ("DEEPSEEK_API_KEY", deepseek_key),
        ]
        if not value
    ]
    if missing:
        raise SystemExit(f".env 缺少必填项: {', '.join(missing)}")

    # 站点间共用同一份 storage_state，但分文件，避免 cookie 串扰
    session_file = SESSION_DIR / f"{site}_storage.json"
    return SzConfig(
        site=site,
        login_url=login_url,
        add_product_url=add_url,
        username=username,
        password=password,
        deepseek_api_key=deepseek_key,
        storage_state_path=session_file,
    )


def find_docx_for_sku(sku: str) -> Optional[Path]:
    """在桌面搜索包含 SKU 的文件夹，返回第一个 .docx。"""
    matches = glob.glob(str(DESKTOP / f"*{sku}*"))
    for m in matches:
        if not os.path.isdir(m):
            continue
        docx_files = [
            f
            for f in glob.glob(os.path.join(m, "*.docx"))
            if not os.path.basename(f).startswith("~")
        ]
        if docx_files:
            return Path(docx_files[0])
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SZ/GD 新品上架（Playwright 有头，完成后人工点保存）"
    )
    parser.add_argument(
        "args",
        nargs="+",
        help="<SKU> 或 <.docx 路径> <SKU>",
    )
    parser.add_argument(
        "--site",
        choices=["sz", "gd"],
        default="sz",
        help="目标站点（默认 sz）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式运行（默认有头）",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="跳过图片上传（只填基础字段 + AI 属性）",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)

    args = parse_args()
    positional = args.args
    site = args.site

    # 解析位置参数
    docx_path: Optional[Path] = None
    sku: Optional[str] = None
    if len(positional) == 1:
        arg = positional[0]
        if os.sep in arg or arg.lower().endswith(".docx"):
            logger.error(
                "只提供了 docx 路径，还需要 SKU：python sz_upload.py <docx> <SKU>"
            )
            return 2
        sku = arg
        docx_path = find_docx_for_sku(sku)
        if docx_path is None:
            logger.error("桌面未找到含 SKU=%s 的文件夹或 .docx", sku)
            return 2
    elif len(positional) >= 2:
        docx_path = Path(positional[0]).expanduser().resolve()
        sku = positional[1]
    else:
        logger.error("参数不足")
        return 2

    logger.info("===== %s 上架开始 =====", site.upper())
    logger.info("docx: %s", docx_path)
    logger.info("SKU : %s", sku)
    logger.info("site: %s", site)

    start_ts = time.time()

    try:
        config = load_config(site)
    except SystemExit:
        raise
    except Exception as e:
        logger.error("配置加载失败: %s", e)
        return 2

    try:
        data = parse_docx(docx_path, sku)
    except DocxParseError as e:
        logger.error("docx 解析失败: %s", e)
        return 3

    filled = sum(1 for v in data.values() if v)
    logger.info("解析完成：%d 个字段非空", filled)
    logger.info("产品: %s", data.get("product_title", "(空)"))
    logger.info("价格: %s", data.get("price", "(空)"))

    # 图片预处理
    image_bundle: Optional[ImageBundle] = None
    if not args.no_images:
        logger.info("开始图片预处理")
        try:
            image_bundle = build_bundle(sku, site)
            if image_bundle.main is None and not image_bundle.listings:
                logger.warning("未找到任何可用图片，流程继续但跳过图片步骤")
                image_bundle = None
            else:
                logger.info(
                    "图片准备完成：主图=%s / listing=%d 张",
                    "有" if image_bundle.main else "无",
                    len(image_bundle.listings),
                )
        except Exception as e:
            logger.error("图片处理失败: %s（继续走无图流程）", e)
            image_bundle = None

    try:
        with SzClient(config, headless=args.headless) as client:
            logger.info("打开 %s 后台并确认登录态", site.upper())
            client.ensure_logged_in()
            logger.info("开始填充字段")
            client.fill_product(data, image_bundle=image_bundle)
            elapsed = time.time() - start_ts
            logger.info("填充完成，耗时 %.1fs", elapsed)
            client.pause_for_manual_save()
            logger.info("用户已关闭浏览器")
    except SzClientError as e:
        logger.error("客户端错误: %s", e)
        return 4
    except KeyboardInterrupt:
        logger.warning("用户中断")
        return 130

    logger.info("===== %s 上架结束 =====", site.upper())
    return 0


if __name__ == "__main__":
    sys.exit(main())
