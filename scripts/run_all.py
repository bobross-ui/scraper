"""Run Stage 1 on all PDFs in data/pdfs/, then build the master CSV.
Usage: uv run scripts/run_all.py [--force]
"""
import argparse

from dotenv import load_dotenv

load_dotenv()

from src.config import PDFS_DIR
from src.csv_builder import build_csv
from src.extractor import extract_pdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-extract even if output exists")
    args = parser.parse_args()

    pdf_paths = sorted(PDFS_DIR.glob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No PDFs found in {PDFS_DIR}")

    total = 0
    for pdf_path in pdf_paths:
        print(f"\n--- {pdf_path.name} ---")
        questions = extract_pdf(pdf_path, force=args.force)
        print(f"  {len(questions)} questions extracted")
        total += len(questions)

    print(f"\nTotal questions extracted: {total}")
    print("\nBuilding master CSV...")
    build_csv()


if __name__ == "__main__":
    main()
