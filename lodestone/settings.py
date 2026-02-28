import os
from pathlib import Path

from platformdirs import user_data_path

LODESTONE_DATA_DIR = os.environ.get("LODESTONE_DATA_DIR")

if LODESTONE_DATA_DIR:
    DATA_PATH = Path(LODESTONE_DATA_DIR)
else:
    DATA_PATH = user_data_path(
        appname="lodestone", appauthor=False, roaming=True, ensure_exists=True
    )

DATA_PATH.mkdir(parents=True, exist_ok=True)

SERVERS_PATH = DATA_PATH / "servers"
LOG_PATH = DATA_PATH / "tui.log"
