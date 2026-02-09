from collections.abc import Callable
from pathlib import Path

import requests

HEADERS = {"User-Agent": "lodestone-server-manager/0.0.1"}

ProgressCb = Callable[[int, int | None], None]


def download_file(
    url: str,
    dest: Path,
    session: requests.Session,
    progress: ProgressCb | None = None,
) -> None:
    with session.get(url, headers=HEADERS, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = (
            int(r.headers["content-length"]) if "content-length" in r.headers else None
        )
        downloaded = 0

        with dest.open("wb") as f:
            for chunk in r.iter_content(8192):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
