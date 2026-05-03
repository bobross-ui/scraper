"""Sample N random questions from extracted JSONLs for manual review.
Usage: uv run scripts/spot_check.py [--count 5] [--pdf cat_2025_slot1_qa.pdf]
"""
import argparse
import json
import random

from src.config import EXTRACTED_DIR
from src.schema import Question


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5, help="Number of questions to sample")
    parser.add_argument("--pdf", help="Restrict to a specific source PDF stem (e.g. cat_2025_slot1_qa)")
    args = parser.parse_args()

    jsonl_files = sorted(EXTRACTED_DIR.glob("*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(f"No extracted JSONL files found in {EXTRACTED_DIR}")

    questions: list[Question] = []
    for jsonl_path in jsonl_files:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            q = Question.model_validate(json.loads(line))
            if args.pdf and args.pdf not in q.source_pdf:
                continue
            questions.append(q)

    if not questions:
        print("No questions matched.")
        return

    sample = random.sample(questions, min(args.count, len(questions)))
    sample.sort(key=lambda q: (q.source_pdf, q.question_number))

    for q in sample:
        print(f"\n{'=' * 60}")
        print(f"Source : {q.source_pdf}  |  Q{q.question_number}  |  {q.type.value} / {q.sub_type.value}")
        print(f"Topic  : {q.sub_topic}")
        print(f"\n{q.text}\n")
        if q.options:
            for i, opt in enumerate(q.options):
                marker = ">>>" if str(i) == q.correct_answer else "   "
                print(f"{marker} {chr(65 + i)}) {opt}")
        else:
            print(f"Answer : {q.correct_answer}")
        print(f"\nExplanation:\n{q.explanation}")


if __name__ == "__main__":
    main()
