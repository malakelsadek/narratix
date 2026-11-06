"""Captures README screenshots into docs/screenshots/ from a running server whose save folder is demo/library.

Start the server first:  NARRATIX_DATA_DIR=demo/library python -m uvicorn narratix.server:app --port 8780
Then:                    python scripts/make_screenshots.py            (needs: pip install playwright)
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8780"
EPUB = ROOT / "demo" / "epubs" / "Deep Work.epub"


def page_for(browser, scheme: str, height: int = 900):  # 16:10 desktop
    ctx = browser.new_context(viewport={"width": 1440, "height": height}, device_scale_factor=2, color_scheme=scheme)
    return ctx.new_page()


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])

    for scheme in ("light", "dark"):
        pg = page_for(browser, scheme)
        pg.goto(URL)
        pg.click("#tab-library")
        pg.wait_for_selector(".lib-card")
        pg.wait_for_timeout(1500)  # let covers load and the entry animation finish
        pg.evaluate("document.getElementById('lib-folder').textContent = '~/Narratix Audiobooks'")  # keep the real path out of screenshots
        pg.screenshot(path=OUT / f"library-{scheme}.png")

        pg.locator(".lib-card", has_text="Deep Work").click()
        pg.wait_for_selector(".chapter-row")
        pg.wait_for_timeout(700)
        pg.click(".chapter-row >> nth=1")  # start playing chapter 2 so the playing state is visible
        pg.wait_for_timeout(1200)
        pg.screenshot(path=OUT / f"book-{scheme}.png")

    pg = page_for(browser, "light")
    pg.goto(URL)
    pg.wait_for_timeout(1500)
    pg.screenshot(path=OUT / "create.png")
    pg.set_input_files("#file-input", str(EPUB))
    pg.wait_for_selector("#voice-card:not(.hidden)")
    pg.wait_for_timeout(1500)
    pg.click(".voice-card >> nth=0")
    pg.evaluate("window.scrollTo(0, document.getElementById('upload-card').offsetTop - 24)")
    pg.wait_for_timeout(500)
    pg.screenshot(path=OUT / "voices.png")

    browser.close()
print("saved to", OUT)
