"""Register package DLL directories before importing PySide6 on Windows."""

from __future__ import annotations

import builtins
import os
import sys
from pathlib import Path


if sys.platform == "win32" and hasattr(sys, "_MEIPASS"):
    bundle_root = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    handles = []
    for package_dir in (bundle_root / "PySide6", bundle_root / "shiboken6"):
        if package_dir.is_dir():
            handles.append(os.add_dll_directory(str(package_dir)))
    # Directory handles must remain alive for the duration of the process.
    builtins._pdf_studio_lite_dll_directories = handles

