from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "video" / "assets" / "plates"

HIDE = """() => {
  const style = document.createElement('style');
  style.textContent = `[data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"],[data-testid="stHeader"],header{display:none!important}`;
  document.head.appendChild(style);
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto("http://localhost:8501", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(9000)
    page.evaluate(HIDE)
    page.get_by_text("Settings / connections", exact=True).click()
    page.wait_for_timeout(2200)
    for name, top in [("52_settings_ai_rows", 150), ("53_settings_ai_rows_low", 230)]:
        page.evaluate("(top) => { const el = document.querySelector('#stMain'); if (el) el.scrollTop = top; }", top)
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    browser.close()
print("done")
