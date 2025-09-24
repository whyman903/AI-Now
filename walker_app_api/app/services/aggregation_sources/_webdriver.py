"""Shared Selenium helpers for aggregation sources."""
from __future__ import annotations

from pathlib import Path

from webdriver_manager.chrome import ChromeDriverManager


def get_chromedriver_path() -> str:
    """Return the executable ChromeDriver path, handling webdriver_manager glitches.

    webdriver_manager 4.0.2 occasionally returns the THIRD_PARTY_NOTICES file from the
    ChromeDriver bundle when running on macOS arm64. That file is not executable, so we
    inspect the parent directory and fall back to the real binary when necessary.
    """
    installed = Path(ChromeDriverManager().install())
    if _ensure_executable(installed):
        return str(installed)

    parent = installed.parent
    # First try the expected names within the same directory.
    for name in ("chromedriver", "chromedriver.exe"):
        candidate = parent / name
        if _ensure_executable(candidate):
            return str(candidate)

    # As a last resort, pick the first executable that resembles chromedriver.
    for candidate in parent.glob("chromedriver*"):
        if _ensure_executable(candidate):
            return str(candidate)

    # Fall back to whatever webdriver_manager gave us; the caller will surface the error.
    return str(installed)


def _ensure_executable(path: Path) -> bool:
    """Confirm the path refers to a chromedriver binary and make it executable if needed."""
    if not path.exists() or not path.is_file():
        return False
    name = path.name
    if name not in {"chromedriver", "chromedriver.exe"}:
        return False

    if path.stat().st_mode & 0o111:
        return True

    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        return False
    return bool(path.stat().st_mode & 0o111)
