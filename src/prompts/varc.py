from src.config import VARC_SUB_TOPICS

VARC_PROMPT = f"""You are extracting questions from a CAT Verbal Ability and Reading Comprehension (VARC) paper.

The PDF contains MCQ and TITA questions, an answer key under "Answers", and worked explanations under "Explanations". Ignore "VIDEO SOLUTION" buttons, Cracku logos, and watermarks.

Four question types appear. Classify each by these rules:
- VARC_RC: questions under an "Instructions [N - M]" header sharing one passage. MCQ, 4 options.
- VARC_ODD_ONE_OUT: "Identify the odd sentence out... key in the number." TITA. 5 sentences given.
- VARC_JUMBLE: "properly sequenced... key in the sequence of the four numbers." TITA. 4 sentences given.
- VARC_MISSING_SENTENCE: "The given sentence is missing in the paragraph below." MCQ, 4 options.

For each question produce JSON with these fields:

1. question_number — integer from "N." at the start.
2. type — "MCQ" for RC and missing-sentence; "TITA" for odd-one-out and jumble.
3. sub_type — one of the four types above (or VARC_SUMMARY / VARC_PARA_COMPLETION if present).
4. text — for VARC_RC: embed the FULL passage verbatim (never truncate) then the question using exactly:
   "[PASSAGE]\\n<passage>\\n\\n[QUESTION]\\n<question>". Repeat the full passage for each question in the group.
   For all other types: the question text including the numbered sentences or paragraph as printed.
5. options — for MCQ: exactly 4 strings in A→D order, without the A/B/C/D labels. For TITA: null.
6. correct_answer —
   - VARC_RC / VARC_MISSING_SENTENCE (MCQ): 0-indexed letter position. "0" for A, "1" for B, "2" for C, "3" for D.
     VARC_MISSING_SENTENCE warning: the options are shuffled (e.g. A=Option 4, B=Option 3). Always output the index of the correct letter, never the paragraph position number. If the answer key says "8.B", output "1" regardless of which position B refers to inside the paragraph.
   - VARC_ODD_ONE_OUT: the odd sentence number as a string. Answer key "1.4" → output "4".
   - VARC_JUMBLE: the full sequence as one string, no spaces or separators. Answer key "6.2143" → output "2143".
7. sub_topic — choose exactly one from: {", ".join(VARC_SUB_TOPICS)}.
8. explanation — compress the source explanation to ~100 words (hard ceiling 130, soft floor 80). Keep critical reasoning; drop restatements. End with one sentence: "The answer is option A/B/C/D." for MCQ, "Sentence N is the odd one out." for odd-one-out, "The correct sequence is WXYZ." for jumbles.

Order questions by question_number ascending. Return JSON matching the provided schema.
"""
