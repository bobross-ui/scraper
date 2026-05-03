from src.schema import Question


def validate(questions: list[Question], answer_key: dict[int, str], stem: str) -> None:
    """Cross-check LLM-extracted questions against the deterministic answer key.

    Hard-fails on count or question-number mismatches (structural problems).
    Flags individual answer mismatches on the Question object and warns; does not raise.
    """
    llm_nums = {q.question_number for q in questions}
    key_nums = set(answer_key.keys())

    if len(questions) != len(answer_key):
        print(
            f"  [WARNING] [{stem}] Question count mismatch: LLM returned {len(questions)}, "
            f"answer key has {len(answer_key)} — continuing"
        )

    if llm_nums != key_nums:
        missing = key_nums - llm_nums
        extra = llm_nums - key_nums
        parts = []
        if missing:
            parts.append(f"missing from LLM: {sorted(missing)}")
        if extra:
            parts.append(f"extra from LLM: {sorted(extra)}")
        print(f"  [WARNING] [{stem}] Question number mismatch — {', '.join(parts)} — continuing")

    for q in questions:
        key_ans = answer_key[q.question_number]

        if len(key_ans) == 1 and key_ans.upper() in "ABCD":
            expected = str(ord(key_ans.upper()) - ord("A"))
        else:
            expected = key_ans

        if q.correct_answer != expected:
            q.answer_mismatch = True
            print(
                f"  [MISMATCH] [{stem}] Q{q.question_number}: LLM said '{q.correct_answer}', "
                f"answer key says '{key_ans}' (expected '{expected}') — flagged"
            )
