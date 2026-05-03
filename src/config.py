from pathlib import Path

# --- Paths ---
ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

PDFS_DIR      = DATA / "pdfs"
EXTRACTED_DIR = DATA / "extracted"
LOGS_DIR      = DATA / "logs"
FINAL_DIR     = DATA / "final"

FINAL_CSV = FINAL_DIR / "questions_master.csv"

# --- Gemini ---
GEMINI_MODEL = "gemini-2.5-flash-lite"

# Pricing as of 2025-05-03 — re-verify quarterly or before a large batch run.
# Source: https://ai.google.dev/gemini-api/docs/pricing
PRICE_INPUT_PER_M  = 0.10   # USD per 1M input tokens (gemini-2.5-flash-lite)
PRICE_OUTPUT_PER_M = 0.40   # USD per 1M output tokens (gemini-2.5-flash-lite)

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

DILR_SUB_TOPICS = [
    "Tables",
    "Bar Charts",
    "Line Graphs",
    "Pie Charts",
    "Venn Diagrams",
    "Logical Puzzles",
    "Arrangements",
    "Games & Tournaments",
    "Networks & Routes",
    "Binary Logic",
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
