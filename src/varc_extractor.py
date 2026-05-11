import hashlib
import re
from pathlib import Path
from typing import Literal

import pdfplumber
from pydantic import BaseModel, Field, ValidationError

from src import answer_key as ak
from src import gemini_client, validator
from src.config import EXTRACTED_DIR, VARC_SUB_TOPICS
from src.prompts.varc import build_varc_prompt
from src.schema import Passage, Question, QuestionCategory, QuestionSubType, QuestionType


_JSON_CTRL_RE = re.compile(r'[\x08\x0c\x0d](?=[a-zA-Z])')
_JSON_CTRL_MAP = {'\x08': '\\b', '\x0c': '\\f', '\x0d': '\\r'}

def _fix_latex(s: str) -> str:
    return _JSON_CTRL_RE.sub(lambda m: _JSON_CTRL_MAP[m.group()], s)


_INSTRUCTIONS_RE = re.compile(r'Instructions\s*\[\s*(\d+)\s*[-–]\s*(\d+)\s*\]', re.IGNORECASE)

def _parse_instruction_ranges(pdf_path: Path) -> list[tuple[int, int]]:
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return [(int(m.group(1)), int(m.group(2))) for m in _INSTRUCTIONS_RE.finditer(text)]


_sub_topic_field = Field(description=f"One of: {', '.join(VARC_SUB_TOPICS)}")


class _RCQuestion(BaseModel):
    question_number: int
    text: str
    options: list[str]
    correct_answer: str
    sub_topic: str = _sub_topic_field
    explanation: str


class _PassageGroup(BaseModel):
    start: int
    end: int
    passage: str
    questions: list[_RCQuestion]


class _OtherQuestion(BaseModel):
    question_number: int
    type: QuestionType
    sub_type: Literal[
        QuestionSubType.VARC_ODD_ONE_OUT,
        QuestionSubType.VARC_JUMBLE,
        QuestionSubType.VARC_MISSING_SENTENCE,
        QuestionSubType.VARC_SUMMARY,
    ]
    text: str
    options: list[str] | None = Field(default=None)
    correct_answer: str
    sub_topic: str = _sub_topic_field
    explanation: str


class _VARCExtraction(BaseModel):
    passage_groups: list[_PassageGroup]
    other_questions: list[_OtherQuestion]


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
    rc_groups = _parse_instruction_ranges(pdf_path)

    try:
        extraction: _VARCExtraction = gemini_client.call(
            prompt=build_varc_prompt(rc_groups),
            schema=_VARCExtraction,
            pdf_bytes=pdf_bytes,
            context={"stem": stem},
        )
    except ValidationError as exc:
        print(f"  [WARNING] [{stem}] Gemini response invalid/truncated — skipping: {exc.error_count()} error(s)")
        return []

    passages: list[Passage] = []
    questions: list[Question] = []

    for group in extraction.passage_groups:
        expected = group.end - group.start + 1
        if len(group.questions) != expected:
            print(f"  [WARNING] [{stem}] RC group [{group.start}-{group.end}] has {len(group.questions)} questions, expected {expected}")

        passage_text = _fix_latex(group.passage)
        passage_id = hashlib.sha256(passage_text.encode()).hexdigest()[:12]
        passages.append(Passage(id=passage_id, text=passage_text, source_pdf=pdf_path.name))

        for q in group.questions:
            questions.append(Question(
                question_number=q.question_number,
                category=QuestionCategory.VARC,
                type=QuestionType.MCQ,
                sub_type=QuestionSubType.VARC_RC,
                text=_fix_latex(q.text),
                options=[_fix_latex(o) for o in q.options],
                correct_answer=q.correct_answer,
                sub_topic=q.sub_topic,
                explanation=_fix_latex(q.explanation),
                source_pdf=pdf_path.name,
                passage_id=passage_id,
            ))

    for q in extraction.other_questions:
        questions.append(Question(
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
        ))

    questions.sort(key=lambda q: q.question_number)

    validator.validate(questions, answer_key, stem)

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(q.model_dump_json() for q in questions) + "\n")
    if passages:
        passages_path = EXTRACTED_DIR / f"{stem}_passages.jsonl"
        passages_path.write_text("\n".join(p.model_dump_json() for p in passages) + "\n")

    return questions
