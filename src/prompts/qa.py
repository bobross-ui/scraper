from src.config import QUANT_SUB_TOPICS

QA_PROMPT = f"""You are extracting questions from a CAT (Common Admission Test) Quantitative Aptitude paper.

The PDF contains MCQ and TITA questions, an answer key under "Answers", and worked explanations under "Explanations". Ignore "VIDEO SOLUTION" buttons, Cracku logos, and watermarks.

MATH FORMATTING — JSON BACKSLASH ESCAPING: LaTeX backslashes MUST be doubled inside JSON strings. `\\f`, `\\t`, `\\b`, `\\r` are JSON control characters that will silently corrupt output. Always write `\\\\frac`, `\\\\sqrt`, `\\\\times`, `\\\\theta`, `\\\\beta`, `\\\\rho`, `\\\\ne`, `\\\\le`, `\\\\ge` (two backslashes in JSON = one LaTeX backslash when parsed).

For each question produce JSON with these fields:

1. question_number — integer N from "N." at the start of the question.
2. type — "MCQ" if four lettered options A-D are shown; "TITA" if a numeric input box is shown (no options).
3. text — cleaned question. Use LaTeX `$...$` for math: `\\\\frac{{a}}{{b}}` for fractions, `\\\\sqrt{{n}}` for radicals, `^` for superscripts, `_` for subscripts. NEVER embed newlines inside `$...$`. Inside math use ASCII operators (`-`, `*`, `/`); outside math use Unicode (` − `, ` × `, ` ÷ `) sparingly.
4. options — for MCQ: exactly 4 strings in A→D order. CRITICAL: if ANY option contains math notation, ALL four must be wrapped in `$...$` for visual consistency.
   - Math example: options conceptually 2, 1/2, -1/2, -2 → output `["$2$", "$\\\\frac{{1}}{{2}}$", "$-\\\\frac{{1}}{{2}}$", "$-2$"]` — bare integers get wrapped alongside their LaTeX siblings. Never use `a/b` for fractions; use `\\\\frac{{a}}{{b}}`.
   - Non-math example: options "always true", "sometimes true", "never true", "cannot be determined" → output `["always true", "sometimes true", "never true", "cannot be determined"]` — no math present, no wrapping needed.
   For TITA: null.
5. correct_answer — read from the "Answers" section. MCQ: output the 0-indexed position of the correct letter: "0" for A, "1" for B, "2" for C, "3" for D. TITA: the numeric answer as a string (e.g. "175", "11.55").
   - Answer mapping example: "1.B" means question 1's answer is B → output `correct_answer: "1"`. "3.6" means question 3 (TITA) has numeric answer 6 → output `correct_answer: "6"`.
6. sub_topic — choose exactly one from: {", ".join(QUANT_SUB_TOPICS)}.
7. explanation — compress the source explanation to ~100 words (hard ceiling 130, soft floor 80). Keep critical reasoning; drop restatements. Use LaTeX with doubled backslashes. End with one sentence stating the answer (e.g. "The answer is $\\\\frac{{1}}{{2}}$.").

Order questions by question_number ascending. Return JSON matching the provided schema.
"""
