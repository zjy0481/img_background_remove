"""目录与文件约定（开发文档第 2 节）。"""

import re
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = ROOT / "source_img"        # 原始图片输入（.jpg/.png）
PROCESSED_DIR = ROOT / "processed_img"  # 去除背景后的成品（PNG）
TEMP_DIR = ROOT / "temp"                # 中间产物 / 缓存 / 备份
BACKUP_DIR = TEMP_DIR / "backup"
ANNOTATIONS_DIR = TEMP_DIR / "annotations"
THUMBNAILS_DIR = TEMP_DIR / "thumbnails"
MODEL_DIR = TEMP_DIR / "models"
NUMBA_CACHE_DIR = TEMP_DIR / "numba_cache"

DIRS = [
    SOURCE_DIR,
    PROCESSED_DIR,
    TEMP_DIR,
    BACKUP_DIR,
    ANNOTATIONS_DIR,
    THUMBNAILS_DIR,
    MODEL_DIR,
    NUMBA_CACHE_DIR,
]

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
THUMB_SIZE = (120, 120)


def ensure_dirs() -> None:
    """确保约定的目录存在。"""
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)


def list_images(directory: Path) -> list:
    """列出目录中的 .jpg/.jpeg/.png 文件名（不区分大小写，按名称排序）。"""
    if not directory.is_dir():
        return []
    names = [
        p.name
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(names)


def source_files() -> list:
    return list_images(SOURCE_DIR)


def processed_files() -> list:
    return list_images(PROCESSED_DIR)


def output_name_for(source_name: str) -> str:
    """开发文档 2.2：原文件名（去扩展名）+ _no_bg.png。"""
    return f"{Path(source_name).stem}_no_bg.png"


def match_source_for(processed_name: str):
    """开发文档 3.2.2-2：去掉 _no_bg 后缀后在 source_img 中匹配原图。"""
    stem = Path(processed_name).stem
    if not stem.endswith("_no_bg"):
        return None
    base = stem[: -len("_no_bg")]
    for cand in source_files():
        if Path(cand).stem == base:
            return cand
    return None


def source_path_for(name: str) -> Path:
    return SOURCE_DIR / name


def processed_path_for(name: str) -> Path:
    return PROCESSED_DIR / name


def round_path_for(processed_name: str, round_no: int) -> Path:
    """开发文档 2.2：temp/<成品名去扩展名>_r{n}.png（如 cat_no_bg_r1.png）。"""
    return TEMP_DIR / f"{Path(processed_name).stem}_r{round_no}.png"


def list_round_files(processed_name: str) -> list:
    """列出某成品已有的精修轮次文件，按轮次升序返回 [(n, Path)]。"""
    stem = Path(processed_name).stem
    pattern = re.compile(re.escape(stem) + r"_r(\d+)\.png$")
    found = []
    for p in TEMP_DIR.iterdir():
        m = pattern.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return sorted(found)


def next_round(processed_name: str) -> int:
    """下一个精修轮次号（r0 视为批量自动结果）。"""
    rounds = list_round_files(processed_name)
    return (rounds[-1][0] + 1) if rounds else 1


def thumbnail_path(kind: str, name: str) -> Path:
    return THUMBNAILS_DIR / f"{kind}__{name}.png"


def ensure_thumbnail(kind: str, name: str) -> Path:
    """生成并缓存约 120×120px 缩略图（开发文档第 9 节默认值）。"""
    out = thumbnail_path(kind, name)
    if out.is_file():
        return out
    src = source_path_for(name) if kind == "source" else processed_path_for(name)
    if not src.is_file():
        raise FileNotFoundError(f"文件不存在：{src}")
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img).convert("RGBA")
        img = ImageOps.fit(img, THUMB_SIZE, method=Image.LANCZOS)
        img.save(out, "PNG")
    return out
