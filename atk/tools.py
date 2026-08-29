"""Process and executable helpers shared by media and download services."""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable


def find_tool(name: str) -> str | None:
    """Return the executable path when a command exists in PATH."""
    return shutil.which(name)


def run_command(command: Iterable[str]) -> subprocess.CompletedProcess[str]:
    """Run a command without opening a console window on Windows."""
    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return subprocess.run(
        list(command), text=True, capture_output=True, check=False, startupinfo=startupinfo
    )
