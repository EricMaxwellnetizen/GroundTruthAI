from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "video" / "clips" / "raw"
SHOTS = ROOT / "video" / "assets" / "screens"
DOWNLOADS = ROOT / "video" / "clips" / "downloads"
for directory in (RAW, SHOTS, DOWNLOADS):
    directory.mkdir(parents=True, exist_ok=True)

CURSOR_JS = r"""
() => {
  if (document.getElementById('gt-cursor')) return;
  const cursor = document.createElement('div');
  cursor.id = 'gt-cursor';
  cursor.style.cssText = [
    'position:fixed','left:50%','top:50%','width:22px','height:22px',
    'border:2px solid rgba(15,118,110,0.95)','border-radius:50%',
    'background:rgba(255,255,255,0.9)','box-shadow:0 0 0 5px rgba(15,118,110,0.16), 0 2px 8px rgba(0,0,0,0.25)',
    'transform:translate(-50%,-50%)','pointer-events:none','z-index:2147483647',
    'transition:left 0.08s linear, top 0.08s linear, opacity 0.15s linear'
  ].join(';');
  document.documentElement.appendChild(cursor);
  document.addEventListener('mousemove', (e) => {
    cursor.style.left = e.clientX + 'px';
    cursor.style.top = e.clientY + 'px';
  }, true);
  document.addEventListener('mousedown', (e) => {
    const r = document.createElement('div');
    r.style.cssText = [
      'position:fixed',`left:${e.clientX}px`,`top:${e.clientY}px`,
      'width:18px','height:18px','border:2px solid rgba(15,118,110,0.8)',
      'border-radius:50%','transform:translate(-50%,-50%) scale(0.6)',
      'pointer-events:none','z-index:2147483646','opacity:1',
      'transition:transform 0.45s ease-out, opacity 0.45s ease-out'
    ].join(';');
    document.documentElement.appendChild(r);
    requestAnimationFrame(() => {
      r.style.transform = 'translate(-50%,-50%) scale(2.8)';
      r.style.opacity = '0';
    });
    setTimeout(() => r.remove(), 600);
  }, true);
}
"""

HIDE_CHROME_JS = r"""
() => {
  const style = document.createElement('style');
  style.id = 'gt-hide-chrome';
  style.textContent = `
    [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
    [data-testid="stHeader"] { display: none !important; }
    header { display: none !important; }
  `;
  document.head.appendChild(style);
}
"""


class Recorder:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.t0 = time.time()
        self.events: list[dict[str, float | str]] = []

    def elapsed(self) -> float:
        return round(time.time() - self.t0, 3)

    def log(self, name: str) -> None:
        self.events.append({"name": name, "t": self.elapsed(), "scroll": self.scroll_y()})
        print(f"[{self.elapsed():7.2f}] {name}")

    def scroll_y(self) -> float:
        try:
            return self.main_scroll_top()
        except Exception:
            return 0.0

    def shot(self, name: str, clean: bool = True) -> None:
        if clean:
            self.page.evaluate(
                "() => { const c = document.getElementById('gt-cursor'); if (c) c.style.opacity = '0'; }"
            )
            self.page.wait_for_timeout(180)
        self.page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
        if clean:
            self.page.evaluate(
                "() => { const c = document.getElementById('gt-cursor'); if (c) c.style.opacity = '1'; }"
            )
        self.log(f"shot_{name}")

    def move_to(self, locator: Locator, steps: int = 24) -> None:
        box = locator.bounding_box()
        if not box:
            return
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=steps)
        self.page.wait_for_timeout(350)

    def click(self, locator: Locator, steps: int = 24) -> None:
        self.move_to(locator, steps=steps)
        self.page.mouse.down()
        self.page.wait_for_timeout(80)
        self.page.mouse.up()
        self.page.wait_for_timeout(250)

    def nav(self, label: str) -> None:
        target = self.page.get_by_text(label, exact=True)
        self.move_to(target)
        self.page.wait_for_timeout(350)
        target.click()
        self.page.wait_for_timeout(2200)

    def scroll(self, pixels: int, steps: int = 14, pause_ms: int = 90) -> None:
        # Streamlit scrolls an inner main container, not window. Drive that
        # element directly so every scroll is reliable regardless of what the
        # pointer happens to be hovering over.
        self.page.evaluate(
            """(pixels) => {
              const selectors = [
                '#stMain',
                '[data-testid="stMain"]',
                '[data-testid="stAppViewContainer"]',
                'section.main',
                'main'
              ];
              let el = null;
              for (const selector of selectors) {
                const candidate = document.querySelector(selector);
                if (candidate && candidate.scrollHeight > candidate.clientHeight + 10) {
                  el = candidate;
                  break;
                }
              }
              if (!el) return;
              const start = el.scrollTop;
              const target = Math.max(0, Math.min(el.scrollHeight - el.clientHeight, start + pixels));
              const t0 = performance.now();
              const duration = 650;
              const tick = (now) => {
                const p = Math.min(1, (now - t0) / duration);
                const eased = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
                el.scrollTop = start + (target - start) * eased;
                if (p < 1) requestAnimationFrame(tick);
              };
              requestAnimationFrame(tick);
            }""",
            pixels,
        )
        self.page.wait_for_timeout(1000)

    def main_scroll_top(self) -> float:
        return float(
            self.page.evaluate(
                """() => {
                  const selectors = ['[data-testid="stMain"]','[data-testid="stAppViewContainer"]','section.main','main'];
                  for (const selector of selectors) {
                    const el = document.querySelector(selector);
                    if (el && el.scrollHeight > el.clientHeight + 10) return el.scrollTop;
                  }
                  return window.scrollY;
                }"""
            )
        )

    def wait_text(self, text: str, timeout_s: float = 180.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if text in self.page.locator("body").inner_text():
                return
            self.page.wait_for_timeout(1000)
        raise TimeoutError(f"Timed out waiting for: {text}")

    def case_button(self, index: int) -> Locator:
        return self.page.locator('[data-testid="stButton"] button').filter(has_text="Run this case").nth(index)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            record_video_dir=str(RAW),
            record_video_size={"width": 1920, "height": 1080},
            accept_downloads=True,
        )
        page = context.new_page()
        rec = Recorder(page)
        page.goto("http://localhost:8501", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        page.evaluate(HIDE_CHROME_JS)
        page.evaluate(CURSOR_JS)
        page.mouse.move(960, 540)
        rec.log("session_start")

        # ---------- Home / overview ----------
        rec.log("scene_home")
        page.wait_for_timeout(1200)
        rec.shot("01_home_hero")
        rec.move_to(page.get_by_text("Find the owner before you touch the resource.", exact=False).first)
        page.wait_for_timeout(1200)
        rec.scroll(240, steps=10)
        page.wait_for_timeout(1000)
        rec.move_to(rec.case_button(0), steps=30)
        page.wait_for_timeout(900)
        rec.shot("02_home_cases")
        rec.log("home_case_a_ready")

        # ---------- Case A: run + progress ----------
        rec.click(rec.case_button(0))
        page.wait_for_timeout(900)
        rec.log("case_a_clicked")
        page.wait_for_timeout(2500)
        rec.shot("03_case_a_progress_early")
        page.wait_for_timeout(5000)
        rec.log("case_a_progress_ai")
        rec.shot("04_case_a_progress_ai")
        page.wait_for_timeout(6000)
        rec.shot("05_case_a_progress_late")
        rec.wait_text("Investigation complete", timeout_s=180)
        page.wait_for_timeout(2200)
        rec.log("case_a_complete")
        rec.shot("06_case_a_complete")
        rec.move_to(page.get_by_text("Current result", exact=True).first)
        page.wait_for_timeout(1200)
        rec.shot("07_case_a_current_result")

        # ---------- Lineage A ----------
        rec.nav("Lineage overview")
        rec.log("lineage_a_top")
        page.wait_for_timeout(900)
        rec.shot("08_lineage_a_top")
        rec.move_to(page.get_by_text("Historical managers", exact=True).first)
        page.wait_for_timeout(700)
        rec.scroll(340, steps=14)
        page.wait_for_timeout(1000)
        rec.shot("09_lineage_a_owner")
        rec.log("lineage_a_owner")
        rec.scroll(360, steps=14)
        page.wait_for_timeout(1000)
        rec.shot("10_lineage_a_repo")
        rec.log("lineage_a_repo")
        rec.scroll(500, steps=18)
        page.wait_for_timeout(1200)
        rec.shot("11_lineage_a_recommendation")
        rec.log("lineage_a_recommendation")
        rec.scroll(500, steps=18)
        page.wait_for_timeout(1200)
        rec.shot("12_lineage_a_gaps")
        rec.log("lineage_a_gaps")

        # ---------- Evidence graph ----------
        rec.nav("Evidence graph")
        rec.log("graph_top")
        page.wait_for_timeout(700)
        rec.shot("13_graph_top")
        rec.scroll(210, steps=10)
        page.wait_for_timeout(900)
        rec.shot("14_graph_chart")
        rec.log("graph_chart")
        # Hover the largest node marker (the Lambda) for the evidence tooltip.
        try:
            markers = page.locator("g.points path")
            boxes = []
            for i in range(min(markers.count(), 80)):
                box = markers.nth(i).bounding_box()
                if box:
                    boxes.append((box["width"] * box["height"], box, i))
            if boxes:
                _, box, index = max(boxes, key=lambda item: item[0])
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=26)
                page.wait_for_timeout(900)
                rec.shot("15_graph_hover", clean=False)
                rec.log("graph_hover")
        except Exception as exc:
            print("graph hover issue:", exc)
        page.wait_for_timeout(900)

        # ---------- Timeline ----------
        rec.nav("Timeline")
        rec.log("timeline_top")
        page.wait_for_timeout(700)
        rec.shot("16_timeline_table")
        rec.scroll(300, steps=12)
        page.wait_for_timeout(900)
        rec.shot("17_timeline_detail")
        rec.log("timeline_detail")
        page.wait_for_timeout(600)

        # ---------- AI explanation ----------
        rec.nav("AI explanation")
        rec.log("ai_top")
        page.wait_for_timeout(900)
        # Muse Spark is live and non-deterministic. If a response fails the
        # product's citation/action guardrails, retry on the same investigation
        # so the recorded demo shows the real successful path.
        for attempt in range(1, 4):
            if page.get_by_text("Deterministic fallback", exact=True).count() == 0:
                break
            print(f"AI fallback detected; regenerating (attempt {attempt})")
            rec.log(f"ai_regenerate_{attempt}")
            button = page.get_by_role("button", name="Regenerate explanation")
            rec.click(button)
            page.wait_for_timeout(1500)
            started = time.time()
            while time.time() - started < 150:
                spinner = page.locator('[data-testid="stSpinner"]').count()
                if spinner == 0:
                    break
                page.wait_for_timeout(1000)
            page.wait_for_timeout(1500)
        if page.get_by_text("Deterministic fallback", exact=True).count() == 0:
            rec.log("ai_muse_spark_success")
        else:
            rec.log("ai_fallback_remains")
        rec.shot("18_ai_top")
        rec.move_to(page.get_by_text("Established facts", exact=True).first)
        page.wait_for_timeout(700)
        rec.scroll(360, steps=14)
        page.wait_for_timeout(900)
        rec.shot("19_ai_facts")
        rec.log("ai_facts")
        rec.scroll(460, steps=16)
        page.wait_for_timeout(1000)
        rec.shot("20_ai_next_steps")
        rec.log("ai_next_steps")
        rec.scroll(360, steps=12)
        page.wait_for_timeout(900)
        rec.shot("21_ai_footer")
        rec.log("ai_footer")

        # ---------- Evidence report + real downloads ----------
        rec.nav("Evidence report")
        rec.log("report_top")
        page.wait_for_timeout(900)
        rec.shot("22_report_top")
        rec.scroll(220, steps=10)
        page.wait_for_timeout(800)
        rec.shot("23_report_contents")
        rec.log("report_contents")
        page.evaluate("() => window.scrollTo({top: 0, behavior: 'instant'})")
        page.wait_for_timeout(1000)
        downloads = page.locator('[data-testid="stDownloadButton"] button')
        print("download buttons:", downloads.count(), downloads.all_inner_texts())
        for index, name in enumerate(["json", "markdown"]):
            try:
                if downloads.count() <= index:
                    continue
                rec.move_to(downloads.nth(index), steps=24)
                page.wait_for_timeout(500)
                with page.expect_download(timeout=15000) as download_info:
                    page.mouse.down()
                    page.wait_for_timeout(80)
                    page.mouse.up()
                download = download_info.value
                target = DOWNLOADS / f"groundtruth_bundle.{name}"
                download.save_as(target)
                rec.log(f"download_{name}")
                page.wait_for_timeout(1300)
            except Exception as exc:
                print(f"download {name} issue:", exc)
        rec.shot("24_report_downloads")
        page.wait_for_timeout(600)

        # ---------- Home, Case B hard stop ----------
        rec.nav("Home / Overview")
        rec.log("home_after_a")
        page.wait_for_timeout(900)
        rec.shot("25_home_after_case_a")
        # Scroll to the case cards and run case B.
        rec.scroll(240, steps=10)
        page.wait_for_timeout(800)
        rec.move_to(rec.case_button(1), steps=30)
        page.wait_for_timeout(900)
        rec.shot("26_home_case_b_ready")
        rec.click(rec.case_button(1))
        page.wait_for_timeout(1000)
        rec.log("case_b_clicked")
        page.wait_for_timeout(3500)
        rec.shot("27_case_b_progress")
        rec.wait_text("Investigation complete", timeout_s=180)
        page.wait_for_timeout(2200)
        rec.log("case_b_complete")
        rec.shot("28_case_b_complete")

        # ---------- Lineage B: conflict + hard stop ----------
        rec.nav("Lineage overview")
        rec.log("lineage_b_top")
        page.wait_for_timeout(900)
        rec.shot("29_lineage_b_top")
        rec.scroll(300, steps=12)
        page.wait_for_timeout(900)
        rec.shot("30_lineage_b_owners")
        rec.log("lineage_b_owners")
        rec.scroll(500, steps=18)
        page.wait_for_timeout(1000)
        rec.shot("31_lineage_b_conflict")
        rec.log("lineage_b_conflict")
        rec.scroll(520, steps=18)
        page.wait_for_timeout(1000)
        rec.shot("32_lineage_b_blocked")
        rec.log("lineage_b_blocked")
        rec.scroll(420, steps=14)
        page.wait_for_timeout(900)
        rec.shot("33_lineage_b_gaps")
        rec.log("lineage_b_gaps")

        # ---------- Settings / connections ----------
        rec.nav("Settings / connections")
        rec.log("settings_top")
        page.wait_for_timeout(900)
        rec.shot("34_settings_top")
        rec.scroll(300, steps=12)
        page.wait_for_timeout(900)
        rec.shot("35_settings_runtime")
        rec.log("settings_runtime")
        rec.scroll(420, steps=16)
        page.wait_for_timeout(1000)
        rec.shot("36_settings_tests")
        rec.log("settings_tests")

        # ---------- Inventory / dependencies ----------
        rec.nav("Resource inventory")
        rec.log("inventory_top")
        page.wait_for_timeout(900)
        rec.shot("37_inventory")
        rec.nav("Dependencies & activity")
        rec.log("dependencies_top")
        page.wait_for_timeout(900)
        rec.shot("38_dependencies")

        # ---------- Home for close ----------
        rec.nav("Home / Overview")
        rec.log("home_close")
        page.wait_for_timeout(1200)
        rec.shot("39_home_close")
        rec.move_to(page.get_by_text("Find the owner before you touch the resource.", exact=False).first)
        page.wait_for_timeout(1400)

        (ROOT / "video" / "clips" / "timeline.json").write_text(json.dumps(rec.events, indent=2), encoding="utf-8")

        video_path = ROOT / "video" / "clips" / "app_flow.webm"
        if page.video is None:
            raise RuntimeError("No video recording available")
        page.close()
        page.video.save_as(video_path)
        context.close()
        browser.close()
        print(f"Saved video: {video_path}")
        print(f"Duration ~{rec.elapsed():.1f}s")


if __name__ == "__main__":
    main()
