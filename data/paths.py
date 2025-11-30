# data/paths.py
import sys
from pathlib import Path

# ---------------------------------------------------------
# DETERMINE ROOT FOLDER (where DB/logs/photos will be stored)
# ---------------------------------------------------------
if getattr(sys, "frozen", False):
    # When packaged with PyInstaller (--onedir):
    # sys.executable == RegisTree/RegisTree.exe
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    # Developer mode:
    # __file__ = RegisTree/data/paths.py → parent(1) = RegisTree/
    ROOT_DIR = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------
# USER-WRITABLE PATHS (DB, exports, logs, photos)
# Always relative to ROOT_DIR, in BOTH dev + exe mode
# ---------------------------------------------------------
DB_PATH      = ROOT_DIR / "registree.db"
EXPORTS_DIR  = ROOT_DIR / "exports"
LOGS_DIR     = ROOT_DIR / "logs"
PHOTOS_DIR   = ROOT_DIR / "photos"
TEACHER_PHOTOS_DIR = PHOTOS_DIR / "teachers"
STUDENT_PHOTOS_DIR = PHOTOS_DIR / "students"

# ---------------------------------------------------------
# APPLICATION RESOURCES (read-only UI, icons, etc.)
# ---------------------------------------------------------
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    APP_ROOT = Path(sys._MEIPASS)
else:
    APP_ROOT = Path(__file__).resolve().parents[1]

UI_DIR     = APP_ROOT / "ui"
ASSETS_DIR = UI_DIR / "assets"
ICON_PATH  = ASSETS_DIR / "registree_icon.png"

# ---------------------------------------------------------
# ENSURE WRITABLE DIRECTORIES EXIST
# ---------------------------------------------------------
for folder in (EXPORTS_DIR, LOGS_DIR, PHOTOS_DIR, TEACHER_PHOTOS_DIR, STUDENT_PHOTOS_DIR):
    folder.mkdir(parents=True, exist_ok=True)
