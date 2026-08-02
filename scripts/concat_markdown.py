"""
Concatenates exam Markdown files from data/processed in reverse chronological order
(most recent -> oldest) into a single file in data/outputs/QA/LEK_all.md.
"""

import re
from pathlib import Path
from typing import Tuple

# Resolve paths relative to project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "data" / "outputs" / "QA"
OUTPUT_FILE = OUTPUT_DIR / "LEK_QA_all.md"


def get_exam_sort_key(file_path: Path) -> Tuple[int, int]:
    """
    Extracts a (year, session_weight) tuple from filenames like 'LEK_jesien_2025.md'.
    - Jesień (Autumn) happens later in the year than Wiosna (Spring).
    - Jesień weight = 2, Wiosna weight = 1.
    """
    filename = file_path.name
    match = re.search(r"LEK_(jesien|wiosna)_(\d{4})", filename, re.IGNORECASE)

    if match:
        session, year = match.groups()
        year_num = int(year)
        session_weight = 2 if session.lower() == "jesien" else 1
        return (year_num, session_weight)

    # Fallback for unformatted files
    return (0, 0)


def concat_markdown_files(
    processed_dir: Path = PROCESSED_DIR, output_file: Path = OUTPUT_FILE
) -> None:
    """
    Finds, sorts, and concatenates all Markdown files into a single master file.
    """
    if not processed_dir.exists():
        print(f"Error: Directory '{processed_dir.relative_to(PROJECT_ROOT)}' does not exist.")
        return

    md_files = list(processed_dir.glob("*.md"))

    if not md_files:
        print(f"No Markdown files found in '{processed_dir.relative_to(PROJECT_ROOT)}'.")
        return

    # Sort files in descending order (Most Recent -> Oldest)
    md_files.sort(key=get_exam_sort_key, reverse=True)

    print(f"Found {len(md_files)} file(s). Order of concatenation:\n")
    for file in md_files:
        print(f"  • {file.name}")

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    concatenated_contents = []

    for file_path in md_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                concatenated_contents.append(content)

    # Join files with clean double newline spacing
    final_markdown = "\n\n".join(concatenated_contents) + "\n"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(final_markdown)

    print(f"\nSuccessfully concatenated {len(md_files)} files to:")
    print(f"  └─ {output_file.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    concat_markdown_files()