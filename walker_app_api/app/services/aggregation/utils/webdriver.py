from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from app.core.config import settings

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_chromedriver_lock = threading.Lock()


def _ensure_executable(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if path.name not in {"chromedriver", "chromedriver.exe"}:
        return False
    if path.stat().st_mode & 0o111:
        return True
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        return False
    return bool(path.stat().st_mode & 0o111)


def get_chromedriver_path() -> str:
    with _chromedriver_lock:
        installed = Path(ChromeDriverManager().install())
        if _ensure_executable(installed):
            return str(installed)

        parent = installed.parent
        for name in ("chromedriver", "chromedriver.exe"):
            candidate = parent / name
            if _ensure_executable(candidate):
                return str(candidate)

        for candidate in parent.glob("chromedriver*"):
            if _ensure_executable(candidate):
                return str(candidate)

        return str(installed)


def create_chrome_driver(
    *,
    headless: bool = True,
    window_size: str = "1400,1000",
    extra_args: Optional[list[str]] = None,
) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(f"--window-size={window_size}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("accept-language=en-US,en;q=0.9")
    opts.add_argument(f"user-agent={DEFAULT_USER_AGENT}")
    if settings.CHROME_BINARY_PATH:
        opts.binary_location = settings.CHROME_BINARY_PATH
    for arg in extra_args or []:
        opts.add_argument(arg)

    service = Service(get_chromedriver_path())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def autoscroll_page(
    driver: webdriver.Chrome,
    *,
    pause: float = 0.9,
    max_attempts: int = 20,
    ensure_stable: bool = True,
    scroll_script: str = "window.scrollTo(0, document.body.scrollHeight);",
    height_script: str = "return document.body.scrollHeight",
) -> None:
    last_height = driver.execute_script(height_script)
    attempts = 0
    while attempts < max_attempts:
        driver.execute_script(scroll_script)
        time.sleep(pause)
        new_height = driver.execute_script(height_script)
        if new_height == last_height:
            if ensure_stable:
                time.sleep(pause)
                new_height = driver.execute_script(height_script)
                if new_height == last_height:
                    break
            else:
                break
        last_height = new_height
        attempts += 1
