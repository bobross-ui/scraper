# VARC Pipeline Plan

Extends the v2 vision pipeline to extract VARC questions. The QA extractor (`src/extractor.py`) is the reference implementation; this plan mirrors its shape with VARC-specific adaptations.

Reference PDF: `data/pdfs/CAT 2025 Slot 1 Question Paper VARC by Cracku.pdf` (24 questions, 28 pages).

---

## Question types observed in the reference PDF

| Sub-type | Description | question_type | Sample answer key |
|---|---|---|---|
| `VARC_RC` | Reading comprehension — multiple questions share one passage | MCQ | `2.D`, `5.A` |
| `VARC_ODD_ONE_OUT` | Five sentences given; identify the one that doesn't belong | TITA | `1.4`, `19.1` |
| `VARC_JUMBLE` | Four sentences given; key in the correct sequence | TITA | `6.2143`, `13.3421` |
| `VARC_MISSING_SENTENCE` | A sentence is missing from a paragraph; pick its position | MCQ | `7.A`, `8.B` |


RC questions are grouped under "Instructions [N - M]" headers. Q2-5, Q9-12, Q14-18, Q20-24 are RC groups in the reference PDF.

---

## What stays unchanged

- `src/schema.py` — `Question` model handles all VARC types. No new fields.
- `src/answer_key.py` — `(\d+)\.(\S+)` regex already captures `1.4`, `6.2143`, `13.3421` correctly. No changes.
- `src/validator.py` — already handles this correctly: single letter A-D → 0-indexed int string; anything else (e.g. `"2143"`, `"1"`, `"4"`) compared verbatim.
- `src/gemini_client.py` — no changes.

---

## `src/prompts/varc.py`

New file. Module-level constant `VARC_PROMPT`.

### RC passage handling

RC questions share a passage that must be embedded in each question's `text` so every question is self-contained in the JSONL. Use a `[PASSAGE]` / `[QUESTION]` delimiter:

```
[PASSAGE]
<full passage text, verbatim, no truncation>

[QUESTION]
<question text>
```

Instruct the LLM: for non-RC questions, `text` contains only the question text (no `[PASSAGE]` prefix).

### TITA answer encoding

Two TITA variants:
- **Odd one out** — output `correct_answer` as the sentence number string, e.g. `"4"` for sentence 4.
- **Para jumble** — output `correct_answer` as the full sequence string, e.g. `"2143"`. No spaces, no separators.

Worked examples for both are mandatory in the prompt — the model needs concrete patterns, not abstract rules.

### MCQ answer encoding

Same as QA: 0-indexed position of the correct letter. `"0"` for A, `"1"` for B, etc. Applies to RC questions and missing-sentence questions alike.

For missing-sentence questions, options in the PDF are labelled A/B/C/D even though they describe position choices ("Option 1", "Option 4", etc.). The LLM still outputs the 0-indexed position of the correct answer letter in the ABCD list, not the position number inside the paragraph. The validator cross-checks against the answer key letter, so this is consistent.

### sub_type taxonomy

Prompt instructs the LLM to assign sub_type per question. Rules:
- Questions under an "Instructions [N-M]" header → `VARC_RC`
- "Identify the odd sentence out" → `VARC_ODD_ONE_OUT`
- "properly sequenced" / "yield a coherent paragraph" with numeric TITA → `VARC_JUMBLE`
- "The given sentence is missing in the paragraph" → `VARC_MISSING_SENTENCE`

The schema Literal enforces this at decode time, catching misclassifications.

### sub_topic

Use `VARC_SUB_TOPICS` from `config.py` (same pattern as QA). RC questions get `"Reading Comprehension"`, para jumbles get `"Para Jumbles"`, etc.

### Explanation

Same instruction as QA: ~100 words, LaTeX with doubled backslashes, end with one sentence naming the answer. For TITA jumble answers, end with: *"The correct sequence is 2143."* For odd one out: *"Sentence 4 is the odd one out."*

---

## `src/varc_extractor.py`

New file. Mirrors `src/extractor.py` exactly, with these VARC-specific differences:

**Schema wrapper** (`_VARCQuestion`):
```python
sub_type: Literal[
    QuestionSubType.VARC_RC,
    QuestionSubType.VARC_JUMBLE,
    QuestionSubType.VARC_ODD_ONE_OUT,
    QuestionSubType.VARC_MISSING_SENTENCE
]
```
All other fields identical to `_QAQuestion`.

**Gemini call:**
```python
gemini_client.call(prompt=VARC_PROMPT, schema=_VARCExtraction, pdf_bytes=pdf_bytes, context={"stem": stem})
```

**Upcast:** `category=QuestionCategory.VARC` (instead of QUANT). `sub_type` taken from the LLM response (not hardcoded — VARC has multiple valid sub_types).

**Output path:** `data/extracted/<stem>.jsonl` — same directory, no change.

**LaTeX fix:** Same `_fix_latex` helper applies (for RC passages that may contain LaTeX in the question text).

---

## Script updates

### `scripts/run_one.py`

Add category dispatch based on filename. If `"VARC"` (case-insensitive) is in the PDF stem, call `varc_extractor.extract_pdf`; otherwise call `extractor.extract_pdf`. Accept an optional `--category` flag to override.

### `scripts/run_all.py`

Same dispatch logic per PDF filename when walking `data/pdfs/`.

No changes to `scripts/spot_check.py` — it reads extracted JSONLs and is category-agnostic.

---

## Diagnostic test cases

After end-to-end extraction on the reference PDF, spot-check these questions:

| Q | Why |
|---|---|
| Q1 | Odd one out, TITA. Expected `correct_answer: "4"`. |
| Q6 | Para jumble, TITA sequence. Expected `correct_answer: "2143"`. |
| Q2 | First RC question. Verify `[PASSAGE]` prefix present in `text`, MCQ options correct. |
| Q7 | Missing sentence MCQ. Options are position labels ("Option 1" etc.). Verify `correct_answer: "0"` (A). |
| Q13 | Para jumble sequence. Expected `correct_answer: "3421"`. |
| Q19 | Odd one out. Expected `correct_answer: "1"`. |

---

## Migration steps, in order

1. Create `src/prompts/varc.py` with `VARC_PROMPT`.
2. Create `src/varc_extractor.py`.
3. Update `scripts/run_one.py` and `scripts/run_all.py` with category dispatch.
4. Run `scripts/run_one.py` on the reference VARC PDF. Check validator passes and JSONL is written.
5. Spot-check the six diagnostic questions above against the source PDF.
6. Run on a second VARC PDF to confirm robustness.

---

## Risks

**RC passage truncation.** Long passages (4-question sets) may push the LLM toward dropping text. Mitigation: no truncation instruction in the prompt — instruct verbatim extraction. If the passage is cut, it will be visible in spot-check.

**TITA sequence misformat.** LLM may output `"21 43"` or `"[2,1,4,3]"` instead of `"2143"`. Mitigation: add a worked example with the exact expected format in the prompt. The validator will catch the mismatch immediately.

**Sub-type misclassification.** Gemini may mis-tag a jumble as RC. Mitigation: the Literal schema restriction + validator makes this a decode error, not a silent wrong value.

**Missing sentence option confusion.** Options are labelled "Option 1/2/3/4" inside the paragraph, then A/B/C/D in the MCQ choices. The LLM must output the A/B/C/D 0-indexed position, not the paragraph position number. Clarify with a worked example in the prompt.
