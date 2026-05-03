from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from src import answer_key as ak
from src import gemini_client, validator
from src.config import EXTRACTED_DIR, QUANT_SUB_TOPICS
from src.prompts.qa import QA_PROMPT
from src.schema import Question, QuestionCategory, QuestionSubType, QuestionType


# QA-specific schema wrapper: sub_type locked to QUANT_STANDARD via Literal.
class _QAQuestion(BaseModel):
    question_number: int
    type: QuestionType
    sub_type: Literal[QuestionSubType.QUANT_STANDARD]
    text: str
    options: list[str] | None = Field(default=None)
    correct_answer: str
    sub_topic: str = Field(description=f"One of: {', '.join(QUANT_SUB_TOPICS)}")
    explanation: str


class _QAExtraction(BaseModel):
    questions: list[_QAQuestion]


def extract_pdf(pdf_path: Path, force: bool = False) -> list[Question]:
    pdf_path = Path(pdf_path)
    stem = pdf_path.stem
    out_path = EXTRACTED_DIR / f"{stem}.jsonl"

    if out_path.exists() and not force:
        questions = [Question.model_validate_json(line) for line in out_path.read_text().splitlines() if line.strip()]
        answer_key = ak.parse(pdf_path)
        validator.validate(questions, answer_key, stem)
        return questions

    pdf_bytes = pdf_path.read_bytes()
    answer_key = ak.parse(pdf_path)

    try:
        extraction: _QAExtraction = gemini_client.call(
            prompt=QA_PROMPT,
            schema=_QAExtraction,
            pdf_bytes=pdf_bytes,
            context={"stem": stem},
        )
    except ValidationError as exc:
        print(f"  [WARNING] [{stem}] Gemini response invalid/truncated — skipping: {exc.error_count()} error(s)")
        return []

    questions = [
        Question(
            question_number=q.question_number,
            category=QuestionCategory.QUANT,
            type=q.type,
            sub_type=QuestionSubType.QUANT_STANDARD,
            text=q.text,
            options=q.options,
            correct_answer=q.correct_answer,
            sub_topic=q.sub_topic,
            explanation=q.explanation,
            source_pdf=pdf_path.name,
        )
        for q in extraction.questions
    ]

    validator.validate(questions, answer_key, stem)

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(q.model_dump_json() for q in questions) + "\n")

    return questions
