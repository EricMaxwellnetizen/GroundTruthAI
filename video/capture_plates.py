from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "video" / "assets" / "plates"
SHOTS.mkdir(parents=True, exist_ok=True)

HIDE_CHROME_JS = r"""
() => {
  const style = document.createElement('style');
  style.id = 'gt-hide-chrome-plates';
  style.textContent = `
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
    [data-testid="stHeader"] { display: none !important; }
    header { display: none !important; }
    #gt-cursor { display: none !important; }
  `;
  document.head.appendChild(style);
}
"""


def scroll_top(page: Page) -> None:
    page.evaluate(
        """() => {
          const el = document.querySelector('#stMain');
          if (el) el.scrollTop = 0;
        }"""
    )
    page.wait_for_timeout(700)


def scroll_to(page: Page, locator: Locator, offset: int = 130) -> None:
    locator.scroll_into_view_if_needed(timeout=15000)
    page.wait_for_timeout(500)
    page.evaluate(
        """(offset) => {
          const el = document.querySelector('#stMain');
          if (el) el.scrollTop = Math.max(0, el.scrollTop - offset);
        }""",
        offset,
    )
    page.wait_for_timeout(800)


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
    print("shot", name)


def run_case(page: Page, index: int) -> None:
    page.get_by_text("Home / Overview", exact=True).click()
    page.wait_for_timeout(1800)
    scroll_top(page)
    buttons = page.locator('[data-testid="stButton"] button').filter(has_text="Run this case")
    buttons.nth(index).scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    buttons.nth(index).click()
    deadline = time.time() + 180
    while time.time() < deadline:
        if page.get_by_text("Investigation complete", exact=False).count():
            break
        page.wait_for_timeout(1000)
    page.wait_for_timeout(2200)


def goto(page: Page, label: str) -> None:
    page.get_by_text(label, exact=True).click()
    page.wait_for_timeout(2000)
    scroll_top(page)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = context.new_page()
        page.goto("http://localhost:8501", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        page.evaluate(HIDE_CHROME_JS)
        scroll_top(page)

        # ---------- Case A ----------
        run_case(page, 0)

        goto(page, "AI explanation")
        # Retry the live model if validation sends it to the deterministic fallback.
        for attempt in range(1, 4):
            if page.get_by_text("Deterministic fallback", exact=True).count() == 0:
                break
            print("fallback detected, regenerating", attempt)
            page.get_by_role("button", name="Regenerate explanation").click()
            page.wait_for_timeout(1800)
            started = time.time()
            while time.time() - started < 150:
                if page.locator('[data-testid="stSpinner"]').count() == 0:
                    break
                page.wait_for_timeout(1000)
            page.wait_for_timeout(1600)
        scroll_top(page)
        shot(page, "40_ai_top_clean")
        scroll_to(page, page.get_by_role("heading", name="Established facts").first)
        shot(page, "41_ai_facts_clean")

        goto(page, "Evidence report")
        shot(page, "42_report_top_clean")
        scroll_to(page, page.get_by_text("SHA-256 integrity checksum", exact=True).first, offset=250)
        shot(page, "43_report_checksum_clean")

        goto(page, "Lineage overview")
        shot(page, "44_lineage_a_top_clean")
        scroll_to(page, page.get_by_role("heading", name="Recommendation").first, offset=260)
        shot(page, "45_lineage_a_recommendation_clean")

        # ---------- Settings ----------
        goto(page, "Settings / connections")
        shot(page, "46_settings_top_clean")

        # ---------- Case B ----------
        run_case(page, 1)

        goto(page, "Lineage overview")
        shot(page, "47_lineage_b_top_clean")
        scroll_to(page, page.get_by_role("heading", name="Recommendation").first, offset=180)
        shot(page, "48_lineage_b_recommendation_clean")
        scroll_to(page, page.get_by_role("heading", name="Coverage gaps").first, offset=180)
        shot(page, "49_lineage_b_gaps_clean")

        browser.close()
        print("done")


if __name__ == "__main__":
    main()
