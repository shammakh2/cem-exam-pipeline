#!/usr/bin/env python3
"""
Polish Medical Exam JSON to Markdown Converter
Converts intermediate JSON files from ./data/intermediates 
into standardized Markdown files in ./data/outputs.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

# Resolve paths relative to project root (parent of scripts/ directory)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

INTERMEDIATES_DIR = PROJECT_ROOT / "data" / "intermediates"
OUTPUTS_DIR = PROJECT_ROOT / "data" / "outputs"


def format_document_title(filename: str) -> str:
    """
    Formats a clean title header from the filename.
    E.g. 'LEK_wiosna_2026.json' -> '# LEK - Lek Wiosna 2026'
    """
    base = Path(filename).stem
    clean = base.replace("_", " ").replace("-", " ").title()

    if clean.upper().startswith("LEK "):
        clean = clean[4:].strip()

    return f"# LEK - Lek {clean}"


def question_to_markdown(q_data: Dict[str, Any], fallback_id: int) -> str:
    """
    Formats a single question dictionary into a Markdown block.
    """
    q_id = q_data.get("question_id") or fallback_id
    stem = (q_data.get("stem") or "").strip()
    sub_statements = q_data.get("sub_statements", [])
    options = q_data.get("options", {})
    correct_ans = q_data.get("correct_answer") or q_data.get("correct_ans")
    warning = q_data.get("warning") or q_data.get("warning_text")

    lines = [f"## Pytanie {q_id}\n"]

    # 1. Stem
    if stem:
        lines.append(stem)
        lines.append("")

    # 2. Sub-statements
    if sub_statements:
        lines.append("\n\n".join(sub_statements))
        lines.append("")

    # 3. Options (A-E) formatted as bullet list
    if options:
        option_lines = []
        for key in sorted(options.keys()):
            option_lines.append(f"- {key}. {options[key]}")

        lines.append("\n".join(option_lines))
        lines.append("")

    # 4. Correct Answer (if present)
    if correct_ans:
        lines.append(f"**Prawidłowa odpowiedź:** {correct_ans}\n")

    # 5. Warning Notice (if present)
    if warning:
        clean_warning = warning.strip()
        if clean_warning.startswith(">"):
            lines.append(f"{clean_warning}\n")
        elif "UWAGA" in clean_warning:
            lines.append(f"> ⚠️ **UWAGA:** {clean_warning}\n")
        else:
            lines.append(f"> ⚠️ **UWAGA:** {clean_warning}\n")

    return "\n".join(lines).strip()


def json_to_markdown_file(json_path: Path, output_md_path: Path) -> None:
    """
    Reads a single JSON file and outputs a formatted Markdown file.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    if not isinstance(questions, list):
        print(f"Skipping {json_path}: Expected a list of question objects.")
        return

    # Ensure parent output directory exists
    output_md_path.parent.mkdir(parents=True, exist_ok=True)

    title_header = format_document_title(json_path.name)
    blocks = [title_header, "\n---\n"]

    for idx, q_data in enumerate(questions, start=1):
        q_md = question_to_markdown(q_data, idx)
        blocks.append(q_md)
        blocks.append("\n---\n")

    full_markdown = "\n".join(blocks).strip() + "\n"

    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(full_markdown)

    print(f"  └─ Generated: {output_md_path.relative_to(PROJECT_ROOT)}")


def process_all_jsons(
    intermediates_dir: Path = INTERMEDIATES_DIR, outputs_dir: Path = OUTPUTS_DIR
) -> None:
    """
    Recursively scans intermediates_dir for JSON files and outputs Markdown to outputs_dir.
    """
    if not intermediates_dir.exists():
        print(f"Directory '{intermediates_dir.relative_to(PROJECT_ROOT)}' does not exist.")
        intermediates_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created '{intermediates_dir.relative_to(PROJECT_ROOT)}'. Place your JSON files here.")
        return

    json_files = list(intermediates_dir.rglob("*.json"))

    if not json_files:
        print(f"No JSON files found in '{intermediates_dir.relative_to(PROJECT_ROOT)}'.")
        return

    print(
        f"Found {len(json_files)} JSON file(s) in '{intermediates_dir.relative_to(PROJECT_ROOT)}'. "
        "Converting to Markdown...\n"
    )

    for json_path in json_files:
        relative_path = json_path.relative_to(intermediates_dir)
        output_md_path = outputs_dir / relative_path.with_suffix(".md")

        try:
            json_to_markdown_file(json_path, output_md_path)
        except Exception as e:
            print(f"Error processing {relative_path}: {e}")

    print("\nConversion complete!")


if __name__ == "__main__":
    process_all_jsons()