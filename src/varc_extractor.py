import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from src import answer_key as ak
from src import gemini_client, validator
from src.config import EXTRACTED_DIR, VARC_SUB_TOPICS
from src.prompts.varc import VARC_PROMPT
from src.schema import Question, QuestionCategory, QuestionSubType, QuestionType


_JSON_CTRL_RE = re.compile(r'[\x08\x0c\x0d](?=[a-zA-Z])')
_JSON_CTRL_MAP = {'\x08': '\\b', '\x0c': '\\f', '\x0d': '\\r'}

def _fix_latex(s: str) -> str:
    return _JSON_CTRL_RE.sub(lambda m: _JSON_CTRL_MAP[m.group()], s)


class _VARCQuestion(BaseModel):
    question_number: int
    type: QuestionType
    sub_type: Literal[
        QuestionSubType.VARC_RC,
        QuestionSubType.VARC_ODD_ONE_OUT,
        QuestionSubType.VARC_JUMBLE,
        QuestionSubType.VARC_MISSING_SENTENCE,
        QuestionSubType.VARC_SUMMARY,
        QuestionSubType.VARC_PARA_COMPLETION,
    ]
    text: str
    options: list[str] | None = Field(default=None)
    correct_answer: str
    sub_topic: str = Field(description=f"One of: {', '.join(VARC_SUB_TOPICS)}")
    explanation: str


class _VARCExtraction(BaseModel):
    questions: list[_VARCQuestion]


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
        extraction: _VARCExtraction = gemini_client.call(
            prompt=VARC_PROMPT,
            schema=_VARCExtraction,
            pdf_bytes=pdf_bytes,
            context={"stem": stem},
        )
    except ValidationError as exc:
        print(f"  [WARNING] [{stem}] Gemini response invalid/truncated — skipping: {exc.error_count()} error(s)")
        return []

    questions = [
        Question(
            question_number=q.question_number,
            category=QuestionCategory.VARC,
            type=q.type,
            sub_type=q.sub_type,
            text=_fix_latex(q.text),
            options=[_fix_latex(o) for o in q.options] if q.options else None,
            correct_answer=q.correct_answer,
            sub_topic=q.sub_topic,
            explanation=_fix_latex(q.explanation),
            source_pdf=pdf_path.name,
        )
        for q in extraction.questions
    ]

    validator.validate(questions, answer_key, stem)

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(q.model_dump_json() for q in questions) + "\n")

    return questions
