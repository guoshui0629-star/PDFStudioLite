from __future__ import annotations

import sys
from pathlib import Path


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    packaged = base / "app" / "resources" / name
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parent / "resources" / name


def ui_resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    packaged = base / "ui" / name
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[1] / "ui" / name
