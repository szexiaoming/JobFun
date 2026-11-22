"""
Phase 3 E2E test: full flow with dialogue + editor UI verification.
"""

import io
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).parent.parent
SAMPLE_ZIP = PROJECT_ROOT / "tests" / "fixtures" / "sample_resume.zip"

SAMPLE_JD = """
Software Engineer at TestCorp
Location: Remote
Requirements:
- 3+ years Python development
- Experience with Docker and Kubernetes
- Experience with message queues (Kafka/RabbitMQ)
- REST API design
Nice to have:
- AWS or GCP experience
"""


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("=" * 60)
    print("Phase 3 E2E Test")
    print("=" * 60)

    errors = []
    browser = None
    proc = None

    try:
        # Already running on 8501 from earlier step
        # Verify it's up
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:8501", timeout=3)
        except Exception:
            print("[FAIL] Streamlit not running on 8501")
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})

            # ── 1. Upload resume ──
            print("\n[1] Uploading resume...")
            page.goto("http://localhost:8501", timeout=15000)
            page.wait_for_selector("text=JobFun", timeout=5000)

            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(str(SAMPLE_ZIP))
            page.click("button:has-text('解析简历')")
            time.sleep(2)

            # Check for success
            success = page.locator("text=解析成功").count()
            print(f"   Resume parse: {'SUCCESS' if success else 'checking...'}")

            # ── 2. Input JD ──
            print("\n[2] Inputting JD...")
            textarea = page.locator("textarea").first
            textarea.fill(SAMPLE_JD)

            # Click parse and wait for result
            page.click("button:has-text('解析 JD（文本）')")
            page.wait_for_timeout(10000)  # Wait for DeepSeek API + Streamlit rerender

            # Check for success message (text may have emoji prefix)
            page_content = page.content()
            jd_success = "TestCorp" in page_content or "Software Engineer" in page_content or "解析完成" in page_content
            print(f"   JD parse: {'SUCCESS' if jd_success else 'not found in page'}")

            # Wait for button or warning to appear
            page.wait_for_timeout(3000)

            # ── 3. Run match analysis ──
            print("\n[3] Running match analysis...")
            match_btn = page.locator("button:has-text('开始匹配分析')")
            warn_msg = page.locator("text=先上传简历并输入 JD")

            if match_btn.count() > 0:
                match_btn.first.click()
                page.wait_for_timeout(25000)  # Wait for DeepSeek reasoner

                has_scores = page.locator("text=总匹配度").count()
                has_skills = page.locator("text=已匹配技能").count()
                print(f"   Match scores: {'YES' if has_scores else 'NO'}")
                print(f"   Skills section: {'YES' if has_skills else 'NO'}")
            elif warn_msg.count() > 0:
                print("   Not ready — JD or resume missing from session state")
            else:
                # Try to see what's on the page
                page.screenshot(path=str(PROJECT_ROOT / "tests" / "screenshots" / "phase3_debug.png"))
                print(f"   Match button absent, screenshot saved")

            # ── 4. Verify dialogue section ──
            print("\n[4] Checking dialogue UI...")
            has_dialogue = page.locator("text=补充经历对话").count()
            has_gap = page.locator("text=针对").count()
            print(f"   Dialogue header: {'YES' if has_dialogue else 'NO'} (count={has_dialogue})")
            print(f"   Gap-fill expanders: {'YES' if has_gap else 'NO'} (count={has_gap})")

            # ── 5. Verify editor section ──
            print("\n[5] Checking editor UI...")
            has_editor = page.locator("text=修改简历").count()
            has_select = page.locator("text=选择要采纳的建议").count()
            has_preview = page.locator("button:has-text('预览修改')").count()
            has_apply = page.locator("button:has-text('执行修改')").count()
            print(f"   Editor header: {'YES' if has_editor else 'NO'} (count={has_editor})")
            print(f"   Suggestion select: {'YES' if has_select else 'NO'} (count={has_select})")
            print(f"   Preview button: {'YES' if has_preview else 'NO'} (count={has_preview})")
            print(f"   Apply button: {'YES' if has_apply else 'NO'} (count={has_apply})")

            # Screenshot
            ss_dir = PROJECT_ROOT / "tests" / "screenshots"
            ss_dir.mkdir(exist_ok=True)
            page.screenshot(path=str(ss_dir / "phase3_full.png"))
            print(f"   Screenshot: phase3_full.png")

            page.screenshot(path=str(PROJECT_ROOT / "tests" / "screenshots" / "phase3_full.png"))

            browser.close()

    except Exception as e:
        errors.append(str(e))
        if browser:
            browser.close()

    # ── Report ──
    print("\n" + "=" * 60)
    if errors:
        print(f"[FAIL] {len(errors)} errors:")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("[OK] Phase 3 E2E test complete")
        return 0


if __name__ == "__main__":
    sys.exit(main())
