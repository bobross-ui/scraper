from src.config import VARC_SUB_TOPICS


def build_varc_prompt(rc_groups: list[tuple[int, int]]) -> str:
    groups_str = ", ".join(f"[{s}-{e}]" for s, e in rc_groups)
    return f"""You are extracting questions from a CAT Verbal Ability and Reading Comprehension (VARC) paper.

The PDF contains MCQ and TITA questions, an answer key under "Answers", and worked explanations under "Explanations". Ignore "VIDEO SOLUTION" buttons, Cracku logos, and watermarks.

The RC passage groups are: {groups_str}. Each group is preceded by an "Instructions [N - M]" header followed by a passage, then the questions for that range.

The response schema has two top-level fields:

**passage_groups** — one entry per RC group listed above, in order. Each entry has:
- start, end: the question number range (integers).
- passage: the full passage text verbatim, extracted once for the group (never truncate).
- questions: exactly (end - start + 1) questions. For each:
  - question_number, text (question only — do not include the passage), options (4 strings A→D order, no labels), correct_answer, sub_topic, explanation.
  - correct_answer: 0-indexed letter — "0" for A, "1" for B, "2" for C, "3" for D.

**other_questions** — every question NOT in an RC group above. Three sub-types:
- VARC_ODD_ONE_OUT: "Identify the odd sentence out... key in the number." TITA. correct_answer = odd sentence number as string e.g. "4".
- VARC_JUMBLE: "properly sequenced... key in the sequence." TITA. correct_answer = full sequence as one unbroken string e.g. "2143".
- VARC_MISSING_SENTENCE: "The given sentence is missing in the paragraph below." MCQ. text includes the given sentence and paragraph with ____(N)____ markers. correct_answer = 0-indexed letter position — options are shuffled, output the letter's index not the paragraph position. Answer key "8.B" → output "1".
- options: 4 strings for MCQ (no labels); null for TITA.

sub_topic for every question — choose exactly one from: {", ".join(VARC_SUB_TOPICS)}.

explanation for every question — ~100 words (ceiling 130, floor 80). Drop restatements. End with: "The answer is option A/B/C/D." for MCQ, "Sentence N is the odd one out." for odd-one-out, "The correct sequence is WXYZ." for jumbles.

Return JSON matching the provided schema.
"""
