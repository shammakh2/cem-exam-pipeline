import os
import re
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

START_URL = "https://cem.edu.pl/pytcem/form_pytania_lek_p.php"
OUTPUT_DIR = os.path.join("data", "processed")

# Map of session form values
SESSIONS_TO_SCRAPE = [
    {"code": "20261", "name": "LEK_wiosna_2026"},
    # {"code": "20252", "name": "LEK_jesien_2025"},
    # {"code": "20251", "name": "LEK_wiosna_2025"},
    # {"code": "20242", "name": "LEK_jesien_2024"},
]


def parse_question_html(html_content: str) -> tuple[str | None, bool]:
    """
    Parses a single LEK question HTML page.
    Returns:
        (markdown_string, is_valid_question)
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Check if we've landed on an end-of-session or error page
    container = soup.find("div", class_="marginesy")
    if not container:
        return None, False

    header = soup.find("center")
    q_num_match = re.search(r"(?:Pytanie nr|Question No\.)\s*(\d+)", header.text) if header else None
    
    # If no question number is found, we reached the end boundary
    if not q_num_match:
        return None, False

    q_num = q_num_match.group(1)

    # 2. Extract Scenario Text and Answer Options
    paragraphs = container.find_all("p")
    q_text_lines = []
    options = []

    for p in paragraphs:
        text = p.text.strip()
        if not text:
            continue

        # Match choice options (e.g., "A. Option text")
        choice_match = re.match(r"^([A-E])\.\s*(.*)", text)
        if choice_match:
            opt_letter, opt_text = choice_match.groups()
            options.append(f"- {opt_letter}. {opt_text}")
        elif not re.search(r"(?:Pytanie nr|Question No\.)", text, re.IGNORECASE):
            q_text_lines.append(text)

    # If no options were found, it's an invalid/blank question page
    if not options:
        return None, False

    # 3. Extract Hidden Correct Answer
    ans_div = soup.find("div", id=re.compile(r"^odpowiedz"))
    correct_ans = ""
    if ans_div:
        ans_match = re.search(r"(?:Prawidłowa odpowiedź to|correct answer is):\s*([A-E])", ans_div.text, re.IGNORECASE)
        if ans_match:
            correct_ans = ans_match.group(1)

    # 4. Check for Inconsistency Warning Label ("Niezgodne z aktualną wiedzą")
    warning_text = ""
    warning_p = soup.find(lambda tag: tag.name == "p" and ("niezgodne z aktualną wiedzą" in tag.text.lower() or "inconsistent with current knowledge" in tag.text.lower()))
    if warning_p:
        warning_text = warning_p.text.strip()

    # 5. Build Structured Markdown Chunk
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


def scrape_lek_all_sessions(sessions: list[dict], max_questions_per_session: int = 200):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-features=Translate",  # Disable auto-translation popup
                "--lang=pl-PL",                  # Keep native Polish text
                "--no-first-run",
            ]
        )

        context = browser.new_context(
            locale="pl-PL",
            extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9"}
        )
        page = context.new_page()

        for idx, session in enumerate(sessions, start=1):
            session_code = session["code"]
            session_name = session["name"]
            out_file = os.path.join(OUTPUT_DIR, f"{session_name}.md")

            print("\n" + "=" * 70)
            print(f"📌 SESSION {idx}/{len(sessions)}: {session_name} (Code: {session_code})")
            print("=" * 70)

            # 1. Navigate to Selection Form
            page.goto(START_URL)
            page.wait_for_selector("#sesja")

            # 2. Select session in dropdown
            page.select_option("#sesja", session_code)
            time.sleep(0.5)

            # 3. Prompt user for captcha solution
            print(f"\n👉 ACTION REQUIRED: Solve reCAPTCHA for '{session_name}' in browser,")
            print("   then click 'Pokaż pytanie'.\n")

            # Wait until form submits to main question page
            page.wait_for_url("**/wyswietl_pytania_lek_p.php", timeout=120000)
            print(f"✅ Session '{session_name}' initialized! Scraping questions...\n")

            session_markdown = []

            # 4. Loop through questions
            for q_num in range(1, max_questions_per_session + 1):
                page.wait_for_selector("div.marginesy")
                html = page.content()

                md_block, is_valid = parse_question_html(html)

                if not is_valid:
                    print(f"ℹ️ Reached end of available questions at #{q_num - 1}.")
                    break

                session_markdown.append(md_block)
                print(f"  ✓ [{session_name}] Scraped Question {q_num}/{max_questions_per_session}")

                # 5. Click Next Question
                next_btn = page.query_selector("input[value='Następne pytanie']") or page.query_selector("input[value='Next question']")
                
                if next_btn and q_num < max_questions_per_session:
                    with page.expect_navigation(wait_until="networkidle"):
                        next_btn.click()
                    time.sleep(0.2)
                else:
                    break

            # 6. Save Session to File
            if session_markdown:
                with open(out_file, "w", encoding="utf-8") as f:
                    file_header = f"# LEK - {session_name.replace('_', ' ').title()}\n\n"
                    f.write(file_header + "\n---\n\n".join(session_markdown))
                print(f"💾 Saved {len(session_markdown)} questions to `{out_file}`")
            else:
                print(f"⚠️ No valid questions scraped for session {session_name}.")

        print("\n🎉 Multi-session extraction completed successfully!")
        browser.close()


if __name__ == "__main__":
    scrape_lek_all_sessions(SESSIONS_TO_SCRAPE)