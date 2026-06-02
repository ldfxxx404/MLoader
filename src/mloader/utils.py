from __future__ import annotations

import re


def safe_filename(value: str) -> str:
    filename = re.sub(r'[\\/:*?"<>|]+', "-", value.strip())
    filename = re.sub(r"\s+", " ", filename)
    return filename.strip(" .") or "download"
