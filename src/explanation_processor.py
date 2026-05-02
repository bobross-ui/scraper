"""Stage 4: compress explanations + assign sub_topic (LLM)."""
import json

from dotenv import load_dotenv
from pydantic import BaseModel

from src import gemini_client
from src.config import (
    ENRICHED_DIR,
    EXTRACTED_DIR,
    PARSED_DIR,
    QUANT_SUB_TOPICS,
    VARC_SUB_TOPICS,
)
from src.schema import (
    EnrichedQuestion,
    ExtractedQuestion,
    ParsedQuestion,
    QuestionCategory,
    QuestionSubType,
)

load_dotenv()

# Expected sub_topic for each VARC sub_type (for consistency logging)
_VARC_SUBTYPE_TOPIC = {
    QuestionSubType.VARC_RC: "Reading Comprehension",
    QuestionSubType.VARC_JUMBLE: "Para Jumbles",
    QuestionSubType.VARC_ODD_ONE_OUT: "Odd One Out",
    QuestionSubType.VARC_MISSING_SENTENCE: "Missing Sentence",
    QuestionSubType.VARC_SUMMARY: "Para Summary",
    QuestionSubType.VARC_PARA_COMPLETION: "Para Completion",
}


class _LLMResponse(BaseModel):
    explanation: str
    sub_topic: str | None


def _build_prompt(q: ExtractedQuestion, raw_explanation: str | None, taxonomy: list[str]) -> str:
    parts = [
        f"sub_type: {q.sub_type.value}",
        f"category: {q.category.value}",
        f"\nQUESTION:\n{q.text}",
    ]

    if q.options:
        for i, opt in enumerate(q.options):
            parts.append(f"Option {chr(65 + i)}: {opt}")

    parts.append(f"\nCORRECT ANSWER: {q.correct_answer}")

    if raw_explanation:
        parts.append(f"\nSOURCE EXPLANATION:\n{raw_explanation}")
    else:
        parts.append(
            "\nSOURCE EXPLANATION: (missing — generate a fresh explanation from the question and correct answer)"
        )

    taxonomy_str = "\n".join(f"  - {t}" for t in taxonomy)
    parts.append(
        f"""
TASKS:
1. COMPRESS the explanation to approximately 100 words (hard ceiling 130 words, soft floor 80 words).
   - Keep all critical reasoning steps. Drop restatements and repetitive algebra.
   - Preserve math in LaTeX: inline $...$, display $$...$$. Never embed newlines inside $...$ or $$...$$.
   - End with one short sentence stating the final answer (e.g. "The answer is $x = 5$.").
   - Voice: direct, imperative ("Apply...", "Substitute...", "Note that...").

2. ASSIGN exactly one sub_topic from this list (or return null if none fits):
{taxonomy_str}

Return JSON with keys: explanation (string), sub_topic (string or null).
"""
    )
    return "\n".join(parts)


def enrich_file(stem: str, force: bool = False) -> list[EnrichedQuestion]:
    """
    Run Stage 4 on a single extracted file identified by its stem.

    Writes:
      data/enriched/<stem>.jsonl        — successful questions
      data/enriched/<stem>.errors.jsonl — failures

    Returns the list of EnrichedQuestion produced.
    """
    extracted_path = EXTRACTED_DIR / f"{stem}.jsonl"
    parsed_path = PARSED_DIR / f"{stem}.json"
    out_path = ENRICHED_DIR / f"{stem}.jsonl"
    err_path = ENRICHED_DIR / f"{stem}.errors.jsonl"

    if not extracted_path.exists():
        raise FileNotFoundError(f"Extracted file not found: {extracted_path}")
    if not parsed_path.exists():
        raise FileNotFoundError(f"Parsed file not found: {parsed_path}")

    extracted = [
        ExtractedQuestion.model_validate(json.loads(line))
        for line in extracted_path.read_text().splitlines()
        if line.strip()
    ]
    parsed_map: dict[int, str | None] = {
        q["question_number"]: q.get("raw_explanation")
        for q in json.loads(parsed_path.read_text())
    }

    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

    # Idempotency: skip if output exists with the right count
    if not force and out_path.exists():
        existing = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
        if len(existing) == len(extracted):
            print(f"[stage4] {stem}: already done ({len(existing)} questions), skipping")
            return [EnrichedQuestion.model_validate(e) for e in existing]

    results: list[EnrichedQuestion] = []
    errors: list[dict] = []

    for q in extracted:
        raw_explanation = parsed_map.get(q.question_number)
        if not raw_explanation:
            print(f"  [warn] Q{q.question_number}: no raw explanation — LLM will generate fresh")

        taxonomy = QUANT_SUB_TOPICS if q.category == QuestionCategory.QUANT else VARC_SUB_TOPICS
        prompt = _build_prompt(q, raw_explanation, taxonomy)

        try:
            llm_out = gemini_client.call(
                prompt,
                _LLMResponse,
                context={"stem": stem, "q": q.question_number},
            )
        except Exception as exc:
            errors.append({"question_number": q.question_number, "error": str(exc)})
            print(f"  [!] Q{q.question_number}: Gemini failed — {exc}")
            continue

        # Consistency check for VARC
        if q.category == QuestionCategory.VARC and q.sub_type in _VARC_SUBTYPE_TOPIC:
            expected = _VARC_SUBTYPE_TOPIC[q.sub_type]
            if llm_out.sub_topic != expected:
                print(
                    f"  [warn] Q{q.question_number}: sub_type={q.sub_type.value} "
                    f"but sub_topic={llm_out.sub_topic!r} (expected {expected!r})"
                )

        try:
            enriched = EnrichedQuestion(
                **q.model_dump(),
                explanation=llm_out.explanation,
                sub_topic=llm_out.sub_topic,
            )
        except Exception as exc:
            errors.append({"question_number": q.question_number, "error": str(exc)})
            print(f"  [!] Q{q.question_number}: validation failed — {exc}")
            continue

        results.append(enriched)
        print(f"  [ok] Q{q.question_number} sub_topic={enriched.sub_topic!r}")

    with open(out_path, "w") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")

    if errors:
        with open(err_path, "w") as f:
            for e in errors:
                f.write(json.dumps(e) + "\n")
        print(f"[stage4] {stem}: {len(results)} ok, {len(errors)} errors → {err_path.name}")
    else:
        print(f"[stage4] {stem}: {len(results)}/{len(extracted)} questions enriched")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 4: compress explanations + assign sub_topic")
    parser.add_argument("stem", help="File stem, e.g. cat_2025_slot1_qa")
    parser.add_argument("--force", action="store_true", help="Re-run even if output exists")
    args = parser.parse_args()

    results = enrich_file(args.stem, force=args.force)
    print(f"\nDone. {len(results)} questions written to data/enriched/{args.stem}.jsonl")
