"""Renders assets/banner.png (2000x1000) and assets/social-preview.png (1280x640) from banner.html

pip install playwright, then: python assets/src/build.py (uses the installed Google Chrome)
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent
OUT = SRC.parent

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    for name, scale in (("banner.png", 1.25), ("social-preview.png", 0.8)):
        page = browser.new_page(viewport={"width": 1600, "height": 800}, device_scale_factor=scale)
        page.goto((SRC / "banner.html").as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(OUT / name))
        page.close()
    browser.close()
print("ok")
