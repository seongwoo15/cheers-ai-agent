from pathlib import Path
import os

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
USER_DATA_DIR = BASE_DIR / "browser_data"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(USER_DATA_DIR, exist_ok=True)

ROW_SELECTOR = "mat-row:not(.read-only)"
DL_SELECTOR = "[data-cy='panel3-download-btn']"
