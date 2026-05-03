"""Standalone cost-test for vision-based PDF extraction via Gemini.

Usage:
    uv run scripts/vision_cost_test.py --pdf data/pdfs/cat_2025_slot1_qa.pdf

Sends the PDF to Gemini 2.5 Flash and asks for the FINAL structured output
(questions, options, answer, sub_topic, compressed explanation) in one shot.
Prints token usage + dollar cost estimate. Output saved as JSON for inspection.

Use this to decide:
  (a) Is vision-only one-shot extraction good enough to replace the entire pipeline?
  (b) If not, is per-question vision fallback affordable?
"""
import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

# gemini-2.5-flash-lite pricing per 1M tokens (paid tier).
# Verify current rates: https://ai.google.dev/gemini-api/docs/pricing
PRICE_INPUT_PER_M = 0.10
PRICE_OUTPUT_PER_M = 0.40

QUANT_SUB_TOPICS = [
    "Algebra", "Arithmetic", "Number Systems", "Geometry", "Mensuration",
    "Trigonometry", "Probability", "Permutations & Combinations",
    "Time & Work", "Time Speed Distance", "Percentages", "Profit & Loss",
    "Simple & Compound Interest", "Ratio & Proportion", "Logarithms",
    "Functions & Graphs", "Sequences & Series", "Mixtures",
]


class Question(BaseModel):
    question_number: int
    type: str = Field(description="MCQ or TITA")
    sub_type: str = Field(description='Always "QUANT_STANDARD" for this paper')
    text: str = Field(description="Cleaned question text. LaTeX math wrapped in $...$.")
    options: list[str] | None = Field(
        description="Exactly 4 strings in A->D order for MCQ. null for TITA."
    )
    correct_answer: str = Field(
        description='MCQ: "0"/"1"/"2"/"3" for A/B/C/D. TITA: numeric string.'
    )
    sub_topic: str = Field(description="One sub-topic from the QUANT taxonomy.")
    explanation: str = Field(description="~100-word LaTeX explanation ending with the answer.")


class Extraction(BaseModel):
    questions: list[Question]


PROMPT = f"""You are extracting questions from a CAT (Common Admission Test) Quantitative Aptitude paper.

The PDF contains MCQ and TITA questions, an answer key under "Answers", and worked explanations under "Explanations". Ignore "VIDEO SOLUTION" buttons, Cracku logos, and watermarks.

For each question produce JSON with these fields:

1. question_number — integer N from "N." at the start of the question.
2. type — "MCQ" if four lettered options A-D are shown; "TITA" if a numeric input box is shown (no options).
3. sub_type — always "QUANT_STANDARD".
4. text — cleaned question. Use LaTeX `$...$` for math: `\\frac{{a}}{{b}}` for fractions, `\\sqrt{{n}}` for radicals, `^` for superscripts, `_` for subscripts. NEVER embed newlines inside `$...$`. Inside math use ASCII operators (`-`, `*`, `/`); outside math use Unicode (` − `, ` × `, ` ÷ `) sparingly.
5. options — for MCQ: exactly 4 strings in A→D order. CRITICAL: if ANY option contains math notation, ALL four must be wrapped in `$...$` for visual consistency. Use `\\frac{{a}}{{b}}` for fractions, never `a/b`. For TITA: null.
6. correct_answer — for MCQ: "0" for A, "1" for B, "2" for C, "3" for D (read from the "Answers" section). For TITA: the numeric answer as a string (e.g. "175", "11.55").
7. sub_topic — choose exactly one from: {", ".join(QUANT_SUB_TOPICS)}.
8. explanation — compress the source explanation to ~100 words (hard ceiling 130, soft floor 80). Keep critical reasoning; drop restatements. Use LaTeX. End with one sentence stating the answer (e.g. "The answer is $\\frac{{1}}{{2}}$.").

Order questions by question_number ascending. Return JSON matching the provided schema.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("vision_test_output.json"))
    args = ap.parse_args()

    if not args.pdf.exists():
        raise FileNotFoundError(args.pdf)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set — copy .env.example to .env and add your key")

    client = genai.Client(api_key=api_key)
    pdf_bytes = args.pdf.read_bytes()
    print(f"PDF: {args.pdf.name}  ({len(pdf_bytes) / 1024:.1f} KB)")
    print(f"Model: gemini-2.5-flash-lite")
    print("Calling Gemini...")

    t0 = time.monotonic()
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Extraction,
        ),
    )
    elapsed = time.monotonic() - t0

    result = Extraction.model_validate_json(response.text)
    args.out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))

    usage = response.usage_metadata
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    in_cost = in_tok * PRICE_INPUT_PER_M / 1_000_000
    out_cost = out_tok * PRICE_OUTPUT_PER_M / 1_000_000

    print(f"\n--- Results ---")
    print(f"Latency       : {elapsed:.1f}s")
    print(f"Questions     : {len(result.questions)}")
    print(f"Input tokens  : {in_tok:>8,}   ${in_cost:.4f}")
    print(f"Output tokens : {out_tok:>8,}   ${out_cost:.4f}")
    print(f"Total cost    : ${in_cost + out_cost:.4f}")
    print(f"Output        : {args.out}")

    # Spot-check the two known-broken cases from the text-only pipeline
    by_num = {q.question_number: q for q in result.questions}
    for n, label in [(1, "stacked fractions"), (4, "dropped √"), (17, "all-fraction options"), (18, "dropped √ in geometry")]:
        q = by_num.get(n)
        if q:
            print(f"\n--- Q{n} ({label}) ---")
            print(json.dumps(q.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()