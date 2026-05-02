from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

PDFS_DIR        = DATA / "pdfs"
RAW_TEXT_DIR    = DATA / "raw_text"
PARSED_DIR      = DATA / "parsed"
ANSWER_KEYS_DIR = DATA / "answer_keys"
EXTRACTED_DIR   = DATA / "extracted"
ENRICHED_DIR    = DATA / "enriched"
LOGS_DIR        = DATA / "logs"
FINAL_DIR       = DATA / "final"

FINAL_CSV = FINAL_DIR / "questions_master.csv"

# --- Gemini ---
GEMINI_MODEL = "gemini-2.5-flash"

# --- Taxonomies ---
QUANT_SUB_TOPICS = [
    "Algebra",
    "Arithmetic",
    "Number Systems",
    "Geometry",
    "Mensuration",
    "Trigonometry",
    "Probability",
    "Permutations & Combinations",
    "Time & Work",
    "Time Speed Distance",
    "Percentages",
    "Profit & Loss",
    "Simple & Compound Interest",
    "Ratio & Proportion",
    "Logarithms",
    "Functions & Graphs",
    "Sequences & Series",
    "Mixtures",
]

VARC_SUB_TOPICS = [
    "Reading Comprehension",
    "Para Jumbles",
    "Para Summary",
    "Odd One Out",
    "Missing Sentence",
    "Para Completion",
    "Critical Reasoning",
    "Vocabulary",
]

# CSV column order expected by the bulk-upload endpoint
CSV_COLUMNS = [
    "type",
    "category",
    "sub_type",
    "sub_topic",
    "difficulty",
    "text",
    "option1",
    "option2",
    "option3",
    "option4",
    "correct_answer",
    "explanation",
]
