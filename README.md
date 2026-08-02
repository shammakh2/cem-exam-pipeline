# CEM Medical Exam Extraction & Processing Pipeline (`cem-exam-tools`)

A modular Python toolchain for scraping, parsing, processing, and standardizing Polish Medical Licensing Exams (**LEK**, **LDEK**, **LEW**, **LDEW**) from official PDFs and the web portal of the Center for Medical Examinations (_Centrum Egzaminów Medycznych_ - CEM).

This repository handles everything from bypassing dynamic web forms and manual reCAPTCHA checkpoints to parsing multi-format exam PDFs, outputting structured JSON, and formatting standardized Markdown datasets for review or LLM fine-tuning.

---

## 🛠 Project Architecture & Data Flow

The repository supports two distinct data ingestion pipelines that converge into a unified Markdown export:

```
                  ┌──────────────────────┐
                  │ Official CEM Website │
                  └──────────┬───────────┘
                             │
                      Playwright Scraper
                (lek_scraper / lew_scraper)
                             │
                             ▼
┌──────────────┐     ┌───────────────┐
│ Raw PDF Files│     │  Live Append  │
└──────┬───────┘     └───────┬───────┘
       │                     │
  PyMuPDF Parser             │
  (pdf_parser.py)            │
       │                     │
       ▼                     │
┌──────────────┐             │
│ Intermediate │             │
│  JSON Files  │             │
└──────┬───────┘             │
       │                     │
   JSON-to-MD                │
(json_to_markdown)           │
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
         ┌────────────────┐
         │ data/processed │
         └───────┬────────┘
                 │
            Concatenator
         (concat_markdown)
                 │
                 ▼
        ┌──────────────────┐
        │   data/outputs   │
        │ (Unified Dataset)│
        └──────────────────┘
```

---

## 📁 Repository Structure

```
.
├── data/
│   ├── raw/                 # Input folder for official PDF exams
│   ├── intermediates/       # Parsed JSON files prior to Markdown conversion
│   ├── processed/           # Individual exam Markdown files (.md)
│   └── outputs/
│       └── QA/              # Concatenated master exam datasets (e.g., LEK_QA_all.md)
├── scripts/
│   ├── cem_scraper.py       # Async Playwright scraper for LEK exams
│   ├── lew_scraper.py       # Async Playwright scraper for LEW / LDEW exams
│   ├── pdf_parser.py        # PyMuPDF parser converting PDFs to intermediate JSON
│   ├── json_to_markdown.py  # Standardized JSON to Markdown converter
│   └── concat_markdown.py   # Chronological dataset aggregator
├── requirements.txt         # Project dependencies
└── README.md
```

---

## ⚙️ Key Features

- **Async Playwright Web Scraping:** Parallelized scraping with user-driven reCAPTCHA pausing, dynamic form interaction (`#sesja`, `#typ`), automatic page transitions, and live streaming-to-disk logic.
- **Robust PDF Structural Parsing:** Extracted via `PyMuPDF` (`fitz`), utilizing regular expressions to separate question stems, embedded sub-statements (`1., 2., 3.`), and multiple-choice options (`A.` through `E.`).
- **Intermediate JSON Schema:** Normalizes exam data across different formats into clean JSON structures.
- **Markdown Formatting Engine:** Converts structured data into standardized Markdown with custom callouts for incorrect or outdated questions (`> ⚠️ **UWAGA:**`).
- **Reverse Chronological Aggregator:** Custom sorting algorithm that parses Polish session names (_Jesień_ / _Wiosna_) and years to build chronological master datasets.

---

## 🚀 Installation & Setup

### 1. Prerequisites

- Python 3.10+
- Google Chrome / Chromium (managed via Playwright)

### 2. Virtual Environment Setup

```bash
# Clone the repository
git clone [https://github.com/your-username/cem-exam-tools.git](https://github.com/your-username/cem-exam-tools.git)
cd cem-exam-tools

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

---

## 📖 How to Use

### Path A: Scraping Exams directly from CEM Portal

1. Configure the session target queue in `scripts/cem_scraper.py` (for LEK) or `scripts/lew_scraper.py` (for LEW).
2. Run the desired scraper script:

   ```bash
   python scripts/cem_scraper.py
   ```

3. **Human In The Loop (reCAPTCHA):**
   - A non-headless browser window will launch and navigate to the portal.
   - The script automatically fills the session parameters.
   - **Solve the reCAPTCHA manually** in the opened browser window and click **"Pokaż pytanie"**.
   - Once solved, the worker detects the navigation change and scrapes all remaining questions automatically, appending them directly to `data/processed/`.

---

### Path B: Processing Official PDF Exams

1. Place your raw exam PDFs inside `data/raw/`.
2. Extract PDF contents into intermediate JSON structures:

   ```bash
   python scripts/pdf_parser.py
   ```

   _Output:_ Saved to `data/intermediates/` as structured `.json` files.

3. Convert intermediate JSONs into standardized Markdown files:

   ```bash
   python scripts/json_to_markdown.py
   ```

   _Output:_ Saved to `data/processed/` as `.md` files.

---

### Path C: Aggregating Master Datasets

To merge all scraped and parsed `.md` files inside `data/processed/` into a single, chronologically sorted master file:

```bash
python scripts/concat_markdown.py
```

- Output file: `data/outputs/QA/LEK_QA_all.md`
- **Sorting order:** Newest to oldest (e.g., `2026 Wiosna` → `2025 Jesień` → `2025 Wiosna` → ... → `2013 Wiosna`).

---

## 🧩 Technical Deep Dive: How It Works

### 1. The Async Web Scraper (`cem_scraper.py` / `lew_scraper.py`)

- Uses **Playwright** with a worker queue pattern.
- Implements a **staggered startup delay** between workers to keep browser instances manageable.
- Features a robust **retry loop** that waits up to 10 minutes per setup attempt, allowing ample time for manual CAPTCHA solving without crashing the script.
- Parses inline HTML via **BeautifulSoup**:
  - Decomposes unnecessary forms, footers, and stats tables.
  - Captures hidden correct answer elements (`div[id^="odpowiedz"]`).
  - Captures medical currency warnings (`"niezgodne z aktualną wiedzą"`).

### 2. PDF Parsing Algorithm (`pdf_parser.py`)

- Reads text blocks page by page using `PyMuPDF`.
- **Lookahead Choice Detection:** Uses lookahead regular expressions (`find_options_start`) to prevent false positives when choices appear within clinical scenario text (e.g., distinguishing between _"podajemy witaminę A."_ in a stem vs Option _"A. podajemy..."_).
- Extracts multi-statement sub-questions (e.g., statements 1 to 5) before extracting choices A–E.

### 3. Chronological Aggregator (`concat_markdown.py`)

Applies a tuple-based weight key function to sort exam filenames:
$$\text{Sort Key} = (\text{Year}, \text{Session Weight})$$
Where:

- **Jesień (Autumn)** = Weight `2`
- **Wiosna (Spring)** = Weight `1`

This guarantees correct ordering even when alphanumeric sorting fails.

---

## 📊 Intermediate JSON Schema

The intermediate JSON format generated by `pdf_parser.py`:

```json
[
  {
    "source_file": "LEK_wiosna_2026.pdf",
    "format_variant": "part_1",
    "raw_header": "Pytanie nr 1",
    "question_id": 1,
    "stem": "Wskazaniem do pilnego wykonania TK głowy jest:",
    "sub_statements": [
      "1. nagły, silny ból głowy.",
      "2. narastające objawy ogniskowe."
    ],
    "options": {
      "A": "tylko 1",
      "B": "tylko 2",
      "C": "1 i 2",
      "D": "żadne z powyższych",
      "E": "wszystkie powyższe"
    }
  }
]
```

---

## 📝 Markdown Standardized Output Example

```markdown
## Pytanie 1

Wskazaniem do pilnego wykonania TK głowy jest:

1. nagły, silny ból głowy.

2. narastające objawy ogniskowe.

- A. tylko 1
- B. tylko 2
- C. 1 i 2
- D. żadne z powyższych
- E. wszystkie powyższe

**Prawidłowa odpowiedź:** C

> ⚠️ **UWAGA:** Pytanie zawiera nieaktualne wytyczne według wiedzy medycznej na rok 2026.
```
