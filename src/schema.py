from enum import Enum
from pydantic import BaseModel, model_validator


class QuestionCategory(str, Enum):
    QUANT = "QUANT"
    VARC = "VARC"
    DILR = "DILR"


class QuestionType(str, Enum):
    MCQ = "MCQ"
    TITA = "TITA"


class QuestionSubType(str, Enum):
    QUANT_STANDARD        = "QUANT_STANDARD"
    VARC_RC               = "VARC_RC"
    VARC_JUMBLE           = "VARC_JUMBLE"
    VARC_ODD_ONE_OUT      = "VARC_ODD_ONE_OUT"
    VARC_MISSING_SENTENCE = "VARC_MISSING_SENTENCE"
    VARC_SUMMARY          = "VARC_SUMMARY"
    VARC_PARA_COMPLETION  = "VARC_PARA_COMPLETION"
    DILR_STANDARD         = "DILR_STANDARD"


class Question(BaseModel):
    question_number: int
    category: QuestionCategory
    type: QuestionType
    sub_type: QuestionSubType
    text: str
    options: list[str] | None
    correct_answer: str
    sub_topic: str | None
    explanation: str
    source_pdf: str
    answer_mismatch: bool = False

    @model_validator(mode="after")
    def check_options_vs_type(self):
        if self.type == QuestionType.MCQ and not self.options:
            raise ValueError("MCQ must have options")
        if self.type == QuestionType.TITA and self.options is not None:
            raise ValueError("TITA must not have options")
        return self


class CSVRow(BaseModel):
    type: QuestionType
    category: QuestionCategory
    sub_type: QuestionSubType
    sub_topic: str | None
    difficulty: int = 3
    text: str
    option1: str = ""
    option2: str = ""
    option3: str = ""
    option4: str = ""
    correct_answer: str
    explanation: str

    @classmethod
    def from_question(cls, q: Question) -> "CSVRow":
        opts = q.options or []
        return cls(
            type=q.type,
            category=q.category,
            sub_type=q.sub_type,
            sub_topic=q.sub_topic,
            text=q.text,
            option1=opts[0] if len(opts) > 0 else "",
            option2=opts[1] if len(opts) > 1 else "",
            option3=opts[2] if len(opts) > 2 else "",
            option4=opts[3] if len(opts) > 3 else "",
            correct_answer=q.correct_answer,
            explanation=q.explanation,
        )
