"""图片预处理：桌面产品文件夹 → 主图方图+水印 / listing 850w+水印。

配置与「暗源新品上架链/sz_listing.py」的 process_images 保持一致，两项目结果对齐。
Logo 跨项目引用 `../网站图片上传/logos/{SZ,GD}_logo.png`。

主图返回临时文件路径（供 Playwright `set_input_files`），
listing 图返回字节（供 Python requests POST 到 editor 端点）。
"""

from __future__ import annotations

import glob
import io
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# 处理参数（对齐油猴脚本 v2.1.0 + 暗源新品上架链 sz_listing.py）
MAIN_IMAGE_SIZE = 500
LISTING_MAX_WIDTH = 850
LOGO_MARGIN = 5
MAIN_LOGO_REL_WIDTH = 0.35
LISTING_LOGO_REL_WIDTH = 0.25
MAIN_QUALITY = 90
LISTING_QUALITY = 100
ARCHIVE_QUALITY = 95  # 本地归档用（对齐 Chrome 插件 ARCHIVE_QUALITY）

PROJECT_DIR = Path(__file__).resolve().parent
LOGOS_DIR = PROJECT_DIR.parent / "网站图片上传" / "logos"
DESKTOP = Path.home() / "Desktop"


class ImageProcessError(Exception):
    """图片处理或定位失败时抛出。"""


@dataclass
class ProcessedMain:
    path: Path
    name: str


@dataclass
class ProcessedListing:
    data: bytes
    name: str


@dataclass
class ImageBundle:
    main: Optional[ProcessedMain] = None
    listings: List[ProcessedListing] = field(default_factory=list)


def load_logo(site: str) -> Optional[Image.Image]:
    """按站点加载 logo。site=sz|gd。"""
    filename = "SZ_logo.png" if site.lower() == "sz" else "GD_logo.png"
    path = LOGOS_DIR / filename
    if not path.exists():
        logger.warning("未找到 logo: %s", path)
        return None
    return Image.open(path).convert("RGBA")


def find_image_folder_for_sku(sku: str) -> Optional[Path]:
    """在桌面搜 `*<SKU>*/` 父文件夹，返回图片所在子目录。

    启发式优先级：
    1. 名为「原图」的子目录
    2. 含 0.jpg/0.png/0.jpeg 的子目录
    3. 第一个非隐藏子目录
    4. 父文件夹本身（如果图直接散在父层）
    """
    matches = [m for m in glob.glob(str(DESKTOP / f"*{sku}*")) if os.path.isdir(m)]
    if not matches:
        return None
    parent = Path(matches[0])

    subdirs = sorted(
        [
            parent / d
            for d in os.listdir(parent)
            if (parent / d).is_dir() and not d.startswith(".")
        ]
    )

    if not subdirs:
        return parent if _folder_has_main(parent) else None

    # 1. 原图 优先
    for sd in subdirs:
        if sd.name == "原图":
            return sd

    # 2. 找含 0.* 的
    for sd in subdirs:
        if _folder_has_main(sd):
            return sd

    # 3. 第一个
    return subdirs[0]


def _folder_has_main(folder: Path) -> bool:
    for ext in ("jpg", "jpeg", "png", "JPG", "JPEG", "PNG"):
        if (folder / f"0.{ext}").exists():
            return True
    return False


def _add_watermark(img: Image.Image, logo: Image.Image, rel_width: float) -> Image.Image:
    """logo 按相对宽度缩放 → 左下角 margin 内叠加。"""
    target_w = int(img.width * rel_width)
    scale = target_w / logo.width
    target_h = int(logo.height * scale)
    logo_resized = logo.resize((target_w, target_h), Image.LANCZOS)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x = LOGO_MARGIN
    y = img.height - target_h - LOGO_MARGIN
    layer.paste(logo_resized, (x, y))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def process_main(
    img_dir: Path, logo: Optional[Image.Image]
) -> Optional[ProcessedMain]:
    """主图：居中正方形 500² + 水印 → JPEG 临时文件。"""
    main_files: List[str] = []
    for ext in ("jpg", "jpeg", "png"):
        main_files.extend(glob.glob(str(img_dir / f"0.{ext}")))
        main_files.extend(glob.glob(str(img_dir / f"0.{ext.upper()}")))
    main_files = sorted(set(main_files))
    if not main_files:
        logger.warning("主图 0.* 未找到: %s", img_dir)
        return None

    src = main_files[0]
    img = Image.open(src)
    size = MAIN_IMAGE_SIZE
    scale = min(size / img.width, size / img.height)
    sw, sh = int(img.width * scale), int(img.height * scale)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    ox = (size - sw) // 2
    oy = (size - sh) // 2
    canvas.paste(img.resize((sw, sh), Image.LANCZOS), (ox, oy))
    if logo is not None:
        canvas = _add_watermark(canvas, logo, MAIN_LOGO_REL_WIDTH)

    tmp_dir = Path(tempfile.gettempdir()) / "sz_upload"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / "main-sq500.jpg"
    canvas.save(tmp_path, "JPEG", quality=MAIN_QUALITY)
    logger.info("主图: %s → %s", os.path.basename(src), tmp_path.name)
    return ProcessedMain(path=tmp_path, name=tmp_path.name)


def _natural_sort_key(path: str) -> Tuple:
    """按文件名中最后一个数字排序，兼容 `X (1).jpg` / `X16.jpg` / `10001.jpg` 等各种命名。"""
    name = os.path.basename(path)
    numbers = re.findall(r"\d+", name)
    num = int(numbers[-1]) if numbers else 0
    return (num, name.lower())


def process_listings(
    img_dir: Path, logo: Optional[Image.Image]
) -> List[ProcessedListing]:
    """listing 图：宽 > 850 则等比缩到 850，附水印 → JPEG 字节。排除 0.*。自然数排序。"""
    all_files: List[str] = []
    for ext in ("jpg", "jpeg", "png"):
        all_files.extend(glob.glob(str(img_dir / f"*.{ext}")))
        all_files.extend(glob.glob(str(img_dir / f"*.{ext.upper()}")))

    all_files = sorted(
        set(
            f
            for f in all_files
            if not os.path.basename(f).startswith("0.")
            and not os.path.basename(f).startswith(".")
        ),
        key=_natural_sort_key,
    )

    results: List[ProcessedListing] = []
    for src in all_files:
        img = Image.open(src)
        if img.width > LISTING_MAX_WIDTH:
            scale = LISTING_MAX_WIDTH / img.width
            img = img.resize(
                (LISTING_MAX_WIDTH, int(img.height * scale)), Image.LANCZOS
            )
        if logo is not None:
            img = _add_watermark(img, logo, LISTING_LOGO_REL_WIDTH)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=LISTING_QUALITY)
        base = os.path.basename(src).rsplit(".", 1)[0]
        results.append(ProcessedListing(data=buf.getvalue(), name=f"{base}-w850.jpg"))

    logger.info("listing: %d 张", len(results))
    return results


def _save_archive_local(
    img_dir: Path, site: str, logo: Optional[Image.Image]
) -> Path:
    """把水印归档图保存到 `{SKU 文件夹}/{SITE}/`，对齐 Chrome 插件的 saveOriginalWithLogoLocal 行为。

    Chrome 插件保存的是**原图分辨率+水印**（`-orig` 后缀，quality 0.95）。
    这里保存两类：
    - 主图：`{SITE}_0-orig.jpg`（原图分辨率+水印，供归档）+ `main-sq500.jpg`（方图版，供上传复用）
    - listing：`{SITE}_{原名}-w850.jpg`（850w+水印，和上传版一致）
    """
    parent = img_dir.parent  # SKU 文件夹
    prefix = site.upper() + "_"
    save_dir = parent / site.upper()
    save_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0

    # 主图原图分辨率+水印归档
    main_files: List[str] = []
    for ext in ("jpg", "jpeg", "png", "JPG", "JPEG", "PNG"):
        main_files.extend(glob.glob(str(img_dir / f"0.{ext}")))
    main_files = sorted(set(main_files))
    if main_files and logo is not None:
        img = Image.open(main_files[0])
        img = _add_watermark(img, logo, MAIN_LOGO_REL_WIDTH)
        out_path = save_dir / f"{prefix}0-orig.jpg"
        img.save(out_path, "JPEG", quality=ARCHIVE_QUALITY)
        saved_count += 1

    # listing 850w+水印
    all_files: List[str] = []
    for ext in ("jpg", "jpeg", "png", "JPG", "JPEG", "PNG"):
        all_files.extend(glob.glob(str(img_dir / f"*.{ext}")))
    all_files = sorted(
        set(
            f
            for f in all_files
            if not os.path.basename(f).startswith("0.")
            and not os.path.basename(f).startswith(".")
        ),
        key=_natural_sort_key,
    )
    for src in all_files:
        img = Image.open(src)
        if img.width > LISTING_MAX_WIDTH:
            scale = LISTING_MAX_WIDTH / img.width
            img = img.resize(
                (LISTING_MAX_WIDTH, int(img.height * scale)), Image.LANCZOS
            )
        if logo is not None:
            img = _add_watermark(img, logo, LISTING_LOGO_REL_WIDTH)
        base = os.path.basename(src).rsplit(".", 1)[0]
        out_path = save_dir / f"{prefix}{base}-w850.jpg"
        img.convert("RGB").save(out_path, "JPEG", quality=LISTING_QUALITY)
        saved_count += 1

    logger.info("本地归档: %d 张 → %s", saved_count, save_dir)
    return save_dir


def build_bundle(sku: str, site: str) -> ImageBundle:
    """一站式：按 SKU 找目录 → 加载 logo → 处理主图 + listing → 保存水印归档 → 返回 bundle。

    找不到目录时返回空 bundle（不抛错，允许脚本继续只做文本填充）。
    水印图同时保存到 `{SKU 文件夹}/{SITE}/` 目录（对齐 Chrome 插件行为）。
    """
    folder = find_image_folder_for_sku(sku)
    if folder is None:
        logger.warning("桌面未找到 %s 的图片目录", sku)
        return ImageBundle()

    logger.info("图片目录: %s", folder)
    logo = load_logo(site)
    main = process_main(folder, logo)
    listings = process_listings(folder, logo)
    _save_archive_local(folder, site, logo)
    return ImageBundle(main=main, listings=listings)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    if len(sys.argv) < 2:
        print("用法: python image_processor.py <SKU> [sz|gd]")
        sys.exit(1)
    site = sys.argv[2] if len(sys.argv) > 2 else "sz"
    bundle = build_bundle(sys.argv[1], site)
    print(f"主图: {bundle.main.path if bundle.main else '无'}")
    print(f"listing: {len(bundle.listings)} 张")
    for l in bundle.listings:
        print(f"  - {l.name} ({len(l.data)} bytes)")
