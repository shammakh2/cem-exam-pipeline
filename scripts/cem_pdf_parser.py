import fitz  # PyMuPDF
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Resolve paths relative to the project root (parent of scripts/ directory)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def find_options_start(text: str) -> int:
    """
    Locates where the answer choices start.
    Requires 'A.' to be followed eventually by 'B.' to avoid false positives 
    like 'witaminę A.' inside the stem text.
    """
    a_matches = list(re.finditer(r'(?:\b|^)A[\.\)]\s+', text))
    for a_m in a_matches:
        a_idx = a_m.start()
        remainder = text[a_idx:]
        if re.search(r'(?:\b|^)B[\.\)]\s+', remainder):
            return a_idx
    return -1


def parse_options(options_text: str) -> Dict[str, str]:
    """
    Parses options (A through E) from either multi-line or inline/horizontal formats.
    """
    options = {}
    if not options_text:
        return options

    pattern = re.compile(
        r'(?:\b|^)([A-E])[\.\)]\s*(.*?)(?=(?:\b[A-E][\.\)]\s*)|$)',
        re.DOTALL
    )

    for match in pattern.finditer(options_text):
        letter = match.group(1).upper()
        content = match.group(2).strip()
        content = re.sub(r'\s+', ' ', content)
        options[letter] = content

    return options


def parse_question_content(raw_body: str) -> Tuple[str, List[str], Dict[str, str]]:
    """
    Splits the body of a question into stem, sub_statements, and options dict.
    """
    options_start_idx = find_options_start(raw_body)

    if options_start_idx != -1:
        pre_option_text = raw_body[:options_start_idx].strip()
        options_text = raw_body[options_start_idx:].strip()
    else:
        pre_option_text = raw_body.strip()
        options_text = ""

    options = parse_options(options_text)
    lines = [line.strip() for line in pre_option_text.split('\n') if line.strip()]

    stem_lines: List[str] = []
    sub_statements: List[str] = []
    in_sub_statements = False
    current_sub_stmt = ""

    sub_stmt_pattern = re.compile(r'^\s*([1-9][0-9]?)[\.\)]\s+(.*)')

    for line in lines:
        match = sub_stmt_pattern.match(line)
        if match:
            in_sub_statements = True
            if current_sub_stmt:
                sub_statements.append(current_sub_stmt)
            current_sub_stmt = f"{match.group(1)}. {match.group(2).strip()}"
        else:
            if in_sub_statements:
                current_sub_stmt += " " + line
            else:
                stem_lines.append(line)

    if current_sub_stmt:
        sub_statements.append(current_sub_stmt)

    stem = re.sub(r'\s+', ' ', " ".join(stem_lines)).strip()

    return stem, sub_statements, options


def extract_questions_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Reads a PDF, extracts text blocks across page breaks, and parses individual questions.
    """
    doc = fitz.open(pdf_path)
    text_blocks: List[str] = []

    for page in doc:
        blocks = page.get_text("blocks")
        for b in blocks:
            if b[6] == 0:  # Text block
                block_text = b[4].strip()
                if re.match(r'^(?:Strona\s+\d+|\d+\s*/\s*\d+|\d+)$', block_text, re.IGNORECASE):
                    continue
                text_blocks.append(block_text)

    full_pdf_text = "\n".join(text_blocks)

    header_pattern = re.compile(
        r'(?:^|\n)\s*(?:(Pytanie\s+nr\s+(\d+))|(Nr\.?\s*(\d+)[\.\s]))',
        re.IGNORECASE
    )

    matches = list(header_pattern.finditer(full_pdf_text))
    questions: List[Dict[str, Any]] = []

    for i in range(len(matches)):
        m = matches[i]
        start_idx = m.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(full_pdf_text)

        raw_q_block = full_pdf_text[start_idx:end_idx].strip()

        raw_header = m.group(0).strip()
        q_id_str = m.group(2) or m.group(4)
        q_id = int(q_id_str) if q_id_str and q_id_str.isdigit() else None

        body_text = raw_q_block[len(raw_header):].strip()
        format_variant = "part_1" if "pytanie" in raw_header.lower() else "part_2"

        stem, sub_statements, options = parse_question_content(body_text)

        q_dict = {
            "source_file": Path(pdf_path).name,
            "format_variant": format_variant,
            "raw_header": raw_header,
            "question_id": q_id,
            "stem": stem,
            "sub_statements": sub_statements,
            "options": options
        }

        questions.append(q_dict)

    return questions


def process_all_pdfs(raw_dir: Path = RAW_DIR, processed_dir: Path = PROCESSED_DIR) -> None:
    """
    Recursively scans raw_dir for all PDFs and outputs JSON files to processed_dir.
    """
    if not raw_dir.exists():
        print(f"Directory '{raw_dir}' does not exist. Creating it now...")
        raw_dir.mkdir(parents=True, exist_ok=True)
        print(f"Please place your PDF files in '{raw_dir}' and run again.")
        return

    pdf_files = list(raw_dir.rglob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in '{raw_dir}'.")
        return

    print(f"Found {len(pdf_files)} PDF file(s) in '{raw_dir}'. Starting parsing...\n")

    for pdf_path in pdf_files:
        relative_path = pdf_path.relative_to(raw_dir)
        output_json_path = processed_dir / relative_path.with_suffix(".json")

        output_json_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            print(f"Processing: {relative_path}")
            questions = extract_questions_from_pdf(str(pdf_path))

            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)

            print(f"  └─ Success: Saved {len(questions)} questions to {output_json_path}\n")
        except Exception as e:
            print(f"  └─ Error processing {relative_path}: {e}\n")


if __name__ == "__main__":
    process_all_pdfs()