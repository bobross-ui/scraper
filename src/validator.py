from src.schema import Question, QuestionType


def validate(questions: list[Question], answer_key: dict[int, str], stem: str) -> None:
    """Cross-check LLM-extracted questions against the deterministic answer key.

    Raises ValueError on any mismatch. Must pass before the JSONL is written.
    """
    llm_nums = {q.question_number for q in questions}
    key_nums = set(answer_key.keys())

    if len(questions) != len(answer_key):
        raise ValueError(
            f"[{stem}] Question count mismatch: LLM returned {len(questions)}, "
            f"answer key has {len(answer_key)}"
        )

    if llm_nums != key_nums:
        missing = key_nums - llm_nums
        extra = llm_nums - key_nums
        parts = []
        if missing:
            parts.append(f"missing from LLM: {sorted(missing)}")
        if extra:
            parts.append(f"extra from LLM: {sorted(extra)}")
        raise ValueError(f"[{stem}] Question number mismatch — {', '.join(parts)}")

    for q in questions:
        key_ans = answer_key[q.question_number]

        if q.type == QuestionType.MCQ:
            expected = str(ord(key_ans.upper()) - ord("A"))
        else:
            expected = key_ans

        if q.correct_answer != expected:
            raise ValueError(
                f"[{stem}] Q{q.question_number}: LLM said '{q.correct_answer}', "
                f"answer key says '{key_ans}' (expected '{expected}')"
            )
