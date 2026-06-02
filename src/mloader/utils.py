from __future__ import annotations

import re

USER_AGENT = "MLoader/0.2.0"


def safe_filename(value: str) -> str:
    filename = re.sub(r'[\\/:*?"<>|]+', "-", value.strip())
    filename = re.sub(r"\s+", " ", filename)
    filename = filename.strip(" .-")
    if not filename or filename in {"CON", "NUL", "PRN", "AUX", "COM1", "COM2", "LPT1", "LPT2"}:
        return "download"
    return filename
