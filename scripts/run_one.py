"""Run Stage 1 (extract) on a single PDF.
Usage: uv run scripts/run_one.py --pdf cat_2025_slot1_qa.pdf [--force]
"""
import argparse

from dotenv import load_dotenv

load_dotenv()

from src.config import PDFS_DIR
from src.extractor import extract_pdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="PDF filename inside data/pdfs/")
    parser.add_argument("--force", action="store_true", help="Re-run even if extracted output exists")
    args = parser.parse_args()

    pdf_path = PDFS_DIR / args.pdf
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    questions = extract_pdf(pdf_path, force=args.force)

    mcq = sum(1 for q in questions if q.type.value == "MCQ")
    tita = sum(1 for q in questions if q.type.value == "TITA")
    print(f"\nExtracted {len(questions)} questions (MCQ={mcq}, TITA={tita})")

    q = questions[0]
    print(f"\n=== Sample: Q{q.question_number} ===")
    print(f"  Type       : {q.type.value} / {q.sub_type.value}")
    print(f"  Sub-topic  : {q.sub_topic}")
    print(f"  Text       : {q.text[:120]}...")
    if q.options:
        for i, opt in enumerate(q.options):
            print(f"  Opt {chr(65 + i)}      : {opt[:80]}")
    print(f"  Answer     : {q.correct_answer}")
    print(f"  Explanation: {q.explanation[:200]}...")


if __name__ == "__main__":
    main()
