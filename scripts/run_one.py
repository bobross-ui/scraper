"""Process a single PDF through all completed stages.
Usage: uv run scripts/run_one.py --pdf cat_2025_slot1_qa.pdf [--force]
"""
import argparse
import json

from dotenv import load_dotenv

load_dotenv()

from src.config import PDFS_DIR
from src.pdf_parser import parse_pdf
from src.block_splitter import parse_blocks
from src.llm_cleaner import clean_file
from src.explanation_processor import enrich_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="PDF filename inside data/pdfs/")
    parser.add_argument("--force", action="store_true", help="Re-run LLM stages even if output exists")
    args = parser.parse_args()

    pdf_path = PDFS_DIR / args.pdf
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    stem = pdf_path.stem

    print("=== Stage 1: PDF → raw text ===")
    raw_path = parse_pdf(pdf_path)
    text = raw_path.read_text()
    print(f"  Output : {raw_path}")
    print(f"  Size   : {len(text):,} chars, {len(text.splitlines())} lines")

    print("\n=== Stage 2: raw text → question blocks ===")
    parsed_path, keys_path = parse_blocks(raw_path, pdf_path.name)
    blocks = json.loads(parsed_path.read_text())
    keys = json.loads(keys_path.read_text())
    mcq = sum(1 for b in blocks if b["type"] == "MCQ")
    tita = sum(1 for b in blocks if b["type"] == "TITA")
    print(f"  Parsed : {parsed_path}")
    print(f"  Keys   : {keys_path}")
    print(f"  Total  : {len(blocks)} questions  (MCQ={mcq}, TITA={tita})")

    print("\n=== Stage 3: clean questions via Gemini ===")
    extracted = clean_file(stem, force=args.force)
    print(f"  Output : data/extracted/{stem}.jsonl")
    print(f"  Total  : {len(extracted)} questions extracted")

    print("\n=== Stage 4: compress explanations + assign sub_topic ===")
    enriched = enrich_file(stem, force=args.force)
    print(f"  Output : data/enriched/{stem}.jsonl")
    print(f"  Total  : {len(enriched)} questions enriched")

    if enriched:
        q = enriched[0]
        print(f"\n=== Sample: Q{q.question_number} ===")
        print(f"  Type       : {q.type.value} / {q.sub_type.value}")
        print(f"  Sub-topic  : {q.sub_topic}")
        print(f"  Text       : {q.text[:120]}...")
        if q.options:
            for i, opt in enumerate(q.options):
                print(f"  Opt {chr(65+i)}      : {opt[:80]}")
        print(f"  Answer     : {q.correct_answer}")
        print(f"  Explanation: {q.explanation[:200]}...")


if __name__ == "__main__":
    main()
