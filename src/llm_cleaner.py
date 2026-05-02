"""Stage 3: raw blocks -> clean structured questions (LLM)."""
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from src import gemini_client
from src.config import ANSWER_KEYS_DIR, EXTRACTED_DIR, PARSED_DIR
from src.schema import (
    ExtractedQuestion,
    ParsedQuestion,
    QuestionCategory,
    QuestionSubType,
    QuestionType,
)

load_dotenv()

MCQ_ANSWER_MAP = {"A": "0", "B": "1", "C": "2", "D": "3"}


def _category_from_sub_type(sub_type: QuestionSubType) -> QuestionCategory:
    if sub_type == QuestionSubType.QUANT_STANDARD:
        return QuestionCategory.QUANT
    if sub_type == QuestionSubType.DILR_STANDARD:
        return QuestionCategory.DILR
    return QuestionCategory.VARC


# Pydantic model for what the LLM returns (text + options only)
class _LLMResponse(BaseModel):
    text: str
    options: list[str] | None


def _build_prompt(q: ParsedQuestion, raw_answer: str) -> str:
    parts = [
        f"sub_type: {q.sub_type.value}",
        f"question_type: {q.type.value}",
    ]

    if q.shared_passage:
        parts.append(f"\nPASSAGE:\n{q.shared_passage}")

    parts.append(f"\nQUESTION TEXT:\n{q.raw_text}")

    if q.raw_options:
        for i, opt in enumerate(q.raw_options):
            parts.append(f"Option {chr(65+i)}: {opt}")

    if q.type == QuestionType.MCQ:
        parts.append(f"\nCORRECT ANSWER LETTER: {raw_answer}")

    if q.raw_explanation:
        parts.append(f"\nEXPLANATION (read-only context — do NOT include in output):\n{q.raw_explanation}")

    parts.append(
        """
TASK:
1. Fix any mangled text: repair null bytes (\\x00), ligature artefacts, broken characters.
2. Fix math: convert broken notation into LaTeX (e.g. x^2, \\frac{1}{2}). Inline math uses $...$; display math uses $$...$$. Never embed newlines inside $...$ or $$...$$.
3. Fix whitespace: normalize multi-line text into clean single strings. For numbered sentence lists (jumbles, odd-one-out), preserve each sentence on its own line.
4. For options: reassemble stacked fractions. Each option must be a complete, self-contained string.
   KNOWN PDF ARTIFACT — stacked fractions: the PDF extractor reads top-to-bottom, so the numerator of a stacked fraction often bleeds into the preceding option's text (e.g. raw options ["2 1", "2 1", "− 2", "−2"] actually represent [2, 1/2, -1/2, -2]). Use the CORRECT ANSWER LETTER and the explanation as cross-checks to reconstruct the true option values.
   KNOWN PDF ARTIFACT — missing numerators: sometimes the numerator appears before the option label (e.g. "27\\nA\\n7" means option A = 27/7, with 27 being the numerator above the fraction bar). Reconstruct from explanation context.
5. KNOWN PDF ARTIFACT — square roots: the PDF extractor drops all √ symbols entirely. A standalone number or a number separated by a space that makes no sense as a plain integer (e.g. "6 2" in a geometry problem, "14" alone in an area formula) likely represents a square root. Use the explanation text to determine the correct radical form and emit it as LaTeX (e.g. $6\\sqrt{2}$, $\\sqrt{14}$).
6. For RC questions (sub_type VARC_RC): merge the passage into `text` using this exact format:
   [PASSAGE]
   {passage}

   [QUESTION]
   {question}
7. For TITA questions: set `options` to null.
8. Return ONLY the JSON — no commentary.
"""
    )
    return "\n".join(parts)


def _strip_latex_newlines(s: str) -> str:
    return re.sub(r'\$([^$]*?)\$', lambda m: '$' + m.group(1).replace('\n', '') + '$', s)


def _merge_answer(raw_answer: str, q_type: QuestionType) -> str:
    if q_type == QuestionType.MCQ:
        return MCQ_ANSWER_MAP.get(raw_answer.upper(), raw_answer)
    return raw_answer  # TITA: verbatim


def clean_file(stem: str, force: bool = False) -> list[ExtractedQuestion]:
    """
    Run Stage 3 on a single parsed file identified by its stem
    (e.g. 'cat_2025_slot1_qa').

    Writes:
      data/extracted/<stem>.jsonl       — successful questions
      data/extracted/<stem>.errors.jsonl — failures

    Returns the list of ExtractedQuestion produced.
    """
    parsed_path = PARSED_DIR / f"{stem}.json"
    key_path = ANSWER_KEYS_DIR / f"{stem}.json"
    out_path = EXTRACTED_DIR / f"{stem}.jsonl"
    err_path = EXTRACTED_DIR / f"{stem}.errors.jsonl"

    if not parsed_path.exists():
        raise FileNotFoundError(f"Parsed file not found: {parsed_path}")
    if not key_path.exists():
        raise FileNotFoundError(f"Answer key not found: {key_path}")

    parsed = [ParsedQuestion.model_validate(q) for q in json.loads(parsed_path.read_text())]
    answer_key: dict[str, str] = json.loads(key_path.read_text())

    # Idempotency: skip if output exists with the right count
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    if not force and out_path.exists():
        existing = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
        if len(existing) == len(parsed):
            print(f"[stage3] {stem}: already done ({len(existing)} questions), skipping")
            return [ExtractedQuestion.model_validate(e) for e in existing]

    results: list[ExtractedQuestion] = []
    errors: list[dict] = []

    for q in parsed:
        raw_answer = answer_key.get(str(q.question_number))
        if raw_answer is None:
            errors.append({"question_number": q.question_number, "error": "missing from answer key"})
            print(f"  [!] Q{q.question_number}: missing from answer key, skipping")
            continue

        prompt = _build_prompt(q, raw_answer)
        try:
            llm_out = gemini_client.call(
                prompt,
                _LLMResponse,
                context={"stem": stem, "q": q.question_number},
            )
        except Exception as exc:
            errors.append({"question_number": q.question_number, "error": str(exc), "raw": q.model_dump()})
            print(f"  [!] Q{q.question_number}: Gemini failed — {exc}")
            continue

        llm_out.text = _strip_latex_newlines(llm_out.text)
        if llm_out.options:
            llm_out.options = [_strip_latex_newlines(o) for o in llm_out.options]

        # Validate options presence matches type
        if q.type == QuestionType.MCQ and not llm_out.options:
            print(f"  [!] Q{q.question_number}: MCQ but LLM returned no options — using raw options as fallback")
            llm_out.options = q.raw_options

        if q.type == QuestionType.TITA:
            llm_out.options = None

        try:
            extracted = ExtractedQuestion(
                question_number=q.question_number,
                category=_category_from_sub_type(q.sub_type),
                type=q.type,
                sub_type=q.sub_type,
                text=llm_out.text,
                options=llm_out.options,
                correct_answer=_merge_answer(raw_answer, q.type),
                source_pdf=q.source_pdf,
            )
        except Exception as exc:
            errors.append({"question_number": q.question_number, "error": str(exc), "llm_out": llm_out.model_dump()})
            print(f"  [!] Q{q.question_number}: validation failed — {exc}")
            continue

        results.append(extracted)
        print(f"  [ok] Q{q.question_number} ({q.type.value}/{q.sub_type.value})")

    # Write outputs
    with open(out_path, "w") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")

    if errors:
        with open(err_path, "w") as f:
            for e in errors:
                f.write(json.dumps(e) + "\n")
        print(f"[stage3] {stem}: {len(results)} ok, {len(errors)} errors → {err_path.name}")
    else:
        print(f"[stage3] {stem}: {len(results)}/{len(parsed)} questions extracted")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 3: clean questions via Gemini")
    parser.add_argument("stem", help="File stem, e.g. cat_2025_slot1_qa")
    parser.add_argument("--force", action="store_true", help="Re-run even if output exists")
    args = parser.parse_args()

    results = clean_file(args.stem, force=args.force)
    print(f"\nDone. {len(results)} questions written to data/extracted/{args.stem}.jsonl")
