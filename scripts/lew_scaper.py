"""
LEW / LDEW Async Scraper (Playwright)
Scrapes LEW exam questions from cem.edu.pl and appends clean Markdown outputs
to data/processed/.
"""

import asyncio
import re
import os
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Resolve project paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

START_URL = "https://cem.edu.pl/pytcem/form_pytania_lew_p.php"
EXAM_TYPE = "LEW"  # "LEW" or "LDEW"

# LEW Exam Sessions Queue
SESSIONS_TO_SCRAPE = [
    {"code": "20211", "name": "LEW_wiosna_2021"},
]

NUM_WORKERS = 2
STAGGER_DELAY = 15
MAX_SESSION_ATTEMPTS = 3


def parse_question_html(html_content: str) -> tuple[str | None, bool]:
    """
    Parses a single LEW question page into clean Markdown.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    container = soup.find("div", class_="marginesy")
    if not container:
        return None, False

    # 1. Extract Question Number & remove header
    header = container.find("center")
    q_num = "X"
    if header:
        q_num_match = re.search(r"(?:Pytanie nr|Question No\.)\s*(\d+)", header.text)
        if q_num_match:
            q_num = q_num_match.group(1)
        header.decompose()

    # 2. Extract Hidden Correct Answer cleanly before decomposing
    ans_div = container.find("div", id=re.compile(r"^odpowiedz"))
    correct_ans = ""
    if ans_div:
        ans_match = re.search(
            r"(?:Prawidłowa odpowiedź to|correct answer is):\s*([A-E])",
            ans_div.text,
            re.IGNORECASE,
        )
        if ans_match:
            correct_ans = ans_match.group(1)
        ans_div.decompose()

    # 3. Extract Warning Notice text cleanly
    warning_text = ""
    for tag in container.find_all(["p", "div", "td"]):
        t_text = tag.text.strip()
        if (
            "niezgodne z aktualną wiedzą" in t_text.lower()
            or "inconsistent with current knowledge" in t_text.lower()
        ):
            if "UWAGA!" in t_text or "NOTE!" in t_text:
                warning_text = " ".join(t_text.split())
                break

    # 4. Decompose non-question DOM elements
    for extra_id in [re.compile(r"^statystyki"), re.compile(r"^uwagi")]:
        for el in container.find_all("div", id=extra_id):
            el.decompose()

    for form in container.find_all("form"):
        form.decompose()

    for row in container.find_all("div", class_="row"):
        row.decompose()

    for btn in container.find_all("input", type=["button", "submit"]):
        btn.decompose()

    # 5. Convert <br> tags into newlines
    for br in container.find_all("br"):
        br.replace_with("\n")

    # 6. Parse clean remaining paragraphs
    paragraphs = container.find_all("p")
    q_text_lines = []
    options = []

    for p in paragraphs:
        text = p.text.strip()
        if not text:
            continue

        if (
            "niezgodne z aktualną wiedzą" in text.lower()
            or "inconsistent with current knowledge" in text.lower()
        ):
            continue
        if "Wskaźnik" in text or "Prosimy o ograniczenie" in text:
            continue

        sub_lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in sub_lines:
            choice_match = re.match(r"^([A-E])\.\s*(.*)", line)
            if choice_match:
                opt_letter, opt_text = choice_match.groups()
                options.append(f"- {opt_letter}. {opt_text}")
            elif not re.search(r"(?:Pytanie nr|Question No\.)", line, re.IGNORECASE):
                q_text_lines.append(line)

    if not options:
        return None, False

    # 7. Format clean Markdown output
    md_lines = [f"## Pytanie {q_num}\n"]

    if q_text_lines:
        md_lines.append("\n\n".join(q_text_lines))
        md_lines.append("\n")

    if options:
        md_lines.append("\n".join(options))
        md_lines.append("\n")

    if correct_ans:
        md_lines.append(f"**Prawidłowa odpowiedź:** {correct_ans}\n")

    if warning_text:
        md_lines.append(f"\n> ⚠️ **UWAGA:** {warning_text}\n")

    return "\n".join(md_lines), True


async def worker_task(
    worker_id: int, queue: asyncio.Queue, playwright, max_questions: int = 200
):
    """Worker process for LEW exam scraping."""
    print(f"🚀 [Worker {worker_id}] Browser starting up...")

    browser = await playwright.chromium.launch(
        headless=False,
        args=[
            "--disable-features=Translate",
            "--lang=pl-PL",
            "--no-first-run",
        ],
    )

    context = await browser.new_context(
        locale="pl-PL", extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9"}
    )
    page = await context.new_page()

    while not queue.empty():
        session = await queue.get()
        session_code = session["code"]
        session_name = session["name"]
        out_file = PROCESSED_DIR / f"{session_name}.md"

        print("\n" + "=" * 60)
        print(f"🔔 [Worker {worker_id}] ATTENTION: Preparing '{session_name}'")
        print("=" * 60 + "\n")

        session_ready = False

        for attempt in range(1, MAX_SESSION_ATTEMPTS + 1):
            print(
                f"🔄 [Worker {worker_id}] Setup attempt {attempt}/{MAX_SESSION_ATTEMPTS} for '{session_name}'..."
            )

            try:
                await page.goto(START_URL)
            except Exception as e:
                print(f"⚠️ [Worker {worker_id}] Failed navigating to {START_URL}: {e}")
                await asyncio.sleep(2)
                continue

            print(f"⏳ [Worker {worker_id}] Waiting for LEW selection form...")
            try:
                await page.wait_for_selector("#sesja", timeout=300000)
                await page.select_option("#sesja", session_code)

                # Select Exam Type (LEW vs LDEW)
                if await page.query_selector("#typ"):
                    await page.select_option("#typ", EXAM_TYPE)

                print(
                    f"  [Worker {worker_id}] Selected session '{session_code}' & type '{EXAM_TYPE}'."
                )
            except Exception:
                print(
                    f"⚠️ [Worker {worker_id}] Timed out waiting for `#sesja` on attempt {attempt}."
                )
                await asyncio.sleep(2)
                continue

            # LEW specific wait URL: wyswietl_pytania_lew_p.php
            print(
                f"👉 [Worker {worker_id}] Solve reCAPTCHA in Browser Window #{worker_id} & click 'Pokaż pytanie'"
            )
            try:
                await page.wait_for_url(
                    "**/wyswietl_pytania_lew_p.php", timeout=600000
                )
                session_ready = True
                break
            except Exception:
                print(
                    f"⚠️ [Worker {worker_id}] Timed out waiting for reCAPTCHA on attempt {attempt}."
                )
                await asyncio.sleep(2)
                continue

        if not session_ready:
            print(
                f"❌ [Worker {worker_id}] Failed setup for {session_name} after {MAX_SESSION_ATTEMPTS} attempts."
            )
            queue.task_done()
            continue

        print(
            f"✅ [Worker {worker_id}] Captcha verified for {session_name}! Starting extraction...\n"
        )

        with open(out_file, "w", encoding="utf-8") as f:
            file_header = f"# LEW - {session_name.replace('_', ' ').title()}\n\n---\n\n"
            f.write(file_header)

        scraped_count = 0

        for q_num in range(1, max_questions + 1):
            await page.wait_for_selector("div.marginesy")
            html = await page.content()

            md_block, is_valid = parse_question_html(html)

            if not is_valid:
                print(
                    f"ℹ️ [Worker {worker_id}] Reached end of questions for {session_name} at Q#{q_num - 1}."
                )
                break

            with open(out_file, "a", encoding="utf-8") as f:
                f.write(md_block + "\n---\n\n")
                f.flush()

            scraped_count += 1
            print(f"  [Worker {worker_id}] Appended Q#{q_num} to `{out_file.name}`")

            next_btn = await page.query_selector(
                "input[value='Następne pytanie']"
            ) or await page.query_selector("input[value='Next question']")

            if next_btn and q_num < max_questions:
                async with page.expect_navigation(wait_until="networkidle"):
                    await next_btn.click()
                await asyncio.sleep(0.15)
            else:
                break

        print(
            f"\n💾 [Worker {worker_id}] COMPLETED {session_name} -> Saved {scraped_count} questions\n"
        )
        queue.task_done()

    print(f"🛑 [Worker {worker_id}] Queue empty. Closing browser.")
    await browser.close()


async def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    queue = asyncio.Queue()
    for session in SESSIONS_TO_SCRAPE:
        await queue.put(session)

    print(
        f"📦 Enqueued {queue.qsize()} LEW exam sessions across {NUM_WORKERS} workers."
    )

    async with async_playwright() as playwright:
        worker_tasks = []
        for i in range(1, NUM_WORKERS + 1):
            if queue.empty():
                break

            task = asyncio.create_task(worker_task(i, queue, playwright))
            worker_tasks.append(task)

            if i < NUM_WORKERS and not queue.empty():
                await asyncio.sleep(STAGGER_DELAY)

        await queue.join()
        await asyncio.gather(*worker_tasks)

    print("\n🎉 All LEW sessions completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())