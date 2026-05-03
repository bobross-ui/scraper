import csv
import json
from pathlib import Path

from src.config import CSV_COLUMNS, EXTRACTED_DIR, FINAL_CSV
from src.schema import CSVRow, Question


def build_csv(output_path: Path = FINAL_CSV) -> None:
    jsonl_files = sorted(EXTRACTED_DIR.glob("*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(f"No extracted JSONL files found in {EXTRACTED_DIR}")

    # Collect all questions; dedupe by (source_pdf, question_number), prefer newest file.
    seen: dict[tuple[str, int], tuple[CSVRow, float]] = {}
    for jsonl_path in jsonl_files:
        mtime = jsonl_path.stat().st_mtime
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            q = Question.model_validate(json.loads(line))
            key = (q.source_pdf, q.question_number)
            if key not in seen or mtime > seen[key][1]:
                seen[key] = (CSVRow.from_question(q), mtime)

    rows = [row for row, _ in seen.values()]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())

    print(f"Wrote {len(rows)} rows to {output_path}")
