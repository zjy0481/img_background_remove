"""目录与文件约定（开发文档第 2 节）。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE_DIR = ROOT / "source_img"        # 原始图片输入（.jpg/.png）
PROCESSED_DIR = ROOT / "processed_img"  # 去除背景后的成品（PNG）
TEMP_DIR = ROOT / "temp"                # 精修中间产物 / 缓存 / 备份
BACKUP_DIR = TEMP_DIR / "backup"
ANNOTATIONS_DIR = TEMP_DIR / "annotations"
THUMBNAILS_DIR = TEMP_DIR / "thumbnails"
MODEL_DIR = TEMP_DIR / "models"

DIRS = [
    SOURCE_DIR,
    PROCESSED_DIR,
    TEMP_DIR,
    BACKUP_DIR,
    ANNOTATIONS_DIR,
    THUMBNAILS_DIR,
    MODEL_DIR,
]


def ensure_dirs() -> None:
    """确保约定的目录存在。"""
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)
