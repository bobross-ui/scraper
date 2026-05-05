"""Run extraction on all PDFs in data/pdfs/.
Usage: uv run scripts/run_all.py
"""
from dotenv import load_dotenv

load_dotenv()

from src.config import PDFS_DIR
from src.extractor import extract_pdf


def main():
    pdf_paths = sorted(PDFS_DIR.glob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No PDFs found in {PDFS_DIR}")

    total = 0
    for pdf_path in pdf_paths:
        print(f"\n--- {pdf_path.name} ---")
        questions = extract_pdf(pdf_path)
        print(f"  {len(questions)} questions extracted")
        total += len(questions)

    print(f"\nTotal: {total} questions across {len(pdf_paths)} PDFs")


if __name__ == "__main__":
    main()
