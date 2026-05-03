# Progress — CAT Question Extractor v2 (Vision Pipeline)

Running log of what's built and how. Read `VISION_PIPELINE_PLAN.md` for the full design; this file tracks execution against it.

---

## Why v2

The text-only pipeline (Stages 1-5, see archived `CAT_Question_Extractor_Execution_Plan.md` and the v1 `PROGRESS.md`) hit a structural ceiling on questions where pdfplumber dropped information that didn't echo elsewhere — Q4 in `cat_2025_slot1_qa.pdf` had √ symbols dropped from both the question and its explanation, leaving the LLM nothing to reconstruct from.

A vision-based one-shot replacement was tested via `scripts/vision_cost_test.py`. Result: 22/22 questions on the same PDF, including Q4 and Q17 (both unfixable in v1), at $0.032 and ~2.3 minutes per PDF. The cost test output is preserved at `vision_test_output.json` for reference.

v2 collapses the old five stages into three (extract, validate, build CSV) and uses Gemini's native PDF input.

---

## Current state

- [x] Branch off main
  - Created `v2` branch off main.
- [x] Rewrite `schema.py` (single `Question` model, drop the per-stage variants)
  - Dropped `ParsedQuestion`, `ExtractedQuestion`, `EnrichedQuestion`. Single `Question` model with all fields. `CSVRow.from_enriched` → `from_question`.
- [x] Rewrite `config.py` (trim to what's actually used, add pricing constants)
  - Dropped old intermediate dirs. Added `PRICE_INPUT_PER_M`, `PRICE_OUTPUT_PER_M`. Added `DILR_SUB_TOPICS`.
- [x] Rewrite `gemini_client.py` (accept optional `pdf_bytes`)
  - Added `pdf_bytes` param; builds `contents` as `[Part.from_bytes(...), prompt]` when provided. Added `pdf_size_bytes` and `cost_usd` to log entries.
- [x] Create `src/prompts/qa.py` (port from cost test, apply three documented changes)
  - Ported from `vision_cost_test.py`. Applied all three changes: (1) math consistency worked example with bare-integer wrapping, (2) non-math options worked example to prevent over-wrapping, (3) answer-letter mapping worked example clarifying 0-indexed encoding. Dropped `sub_type` field from prompt — enforced via schema (Literal) in extractor instead.
- [x] Create `src/answer_key.py` (deterministic regex parser)
  - `parse(pdf_path) -> dict[int, str]`. Locates `Answers...Explanations` slice via pdfplumber, runs `(\d+)\.(\S+)` regex. Smoke-tested on reference PDF: 22/22 answers, Q1→B, Q4→A, Q17→D, Q18→C all correct.
- [x] Create `src/validator.py` (cross-check LLM answers against parsed key)
  - `validate(questions, answer_key, stem) -> None`. Three hard-fail checks: count match, question-number set match, per-question answer match (maps key letters A-D → "0"-"3" for MCQ, verbatim for TITA). Tested: passes on reference output (22/22), raises with clear message on deliberate mismatch.
- [x] Create `src/extractor.py` (Stage 1 — the only LLM stage)
  - `extract_pdf(pdf_path, force=False) -> list[Question]`. Idempotent: loads from JSONL if exists (re-validates on load). Fresh run: reads PDF bytes, parses answer key, calls Gemini with `_QAExtraction` schema (sub_type locked via `Literal[QUANT_STANDARD]`), upcasts to `Question`, validates, writes JSONL atomically only after validation passes.
- [x] Create `src/csv_builder.py` (Stage 3 — final CSV emission)
  - `build_csv(output_path=FINAL_CSV) -> None`. Globs `data/extracted/*.jsonl`, deserialises each line into `Question`, converts via `CSVRow.from_question`, dedupes by `(source_pdf, question_number)` preferring newest mtime, writes UTF-8 CSV with `QUOTE_ALL` and `CSV_COLUMNS` ordering.
- [x] Rewrite `scripts/run_one.py`, `scripts/run_all.py`
  - `run_one.py`: calls `extract_pdf`, prints count + sample question. `run_all.py`: walks all PDFs in `data/pdfs/`, extracts each, then calls `build_csv` once at the end.
- [x] Add `scripts/spot_check.py`
  - Samples N random questions from extracted JSONLs, pretty-prints with correct answer marked (`>>>`). Optional `--pdf` filter to restrict to one source.
- [x] Delete old stage modules and directories
  - Removed `block_splitter.py`, `explanation_processor.py`, `llm_cleaner.py`, `pdf_parser.py` from `src/`. Deleted `data/raw_text/`, `data/parsed/`, `data/answer_keys/`, `data/enriched/`.
- [x] Validate against `cat_2025_slot1_qa.pdf` end-to-end
  - Fixed truncation: `thinking_budget=0` in `gemini_client.py` disables thinking tokens, freeing the full 65,536 output token budget. Fixed validator to flag answer mismatches softly (sets `answer_mismatch=True` on the `Question`) instead of hard-failing. Added `answer_mismatch: bool = False` field to `Question` schema. Diagnostic cases Q1/Q4/Q17/Q18 all pass. 22/22 extracted, JSONL written.
- [ ] Validate against second and third PDFs
- [ ] Smoke-test one CSV row through bulk-upload endpoint
- [ ] Merge to main

---

## Cost test findings (informs prompt design)

Run on `cat_2025_slot1_qa.pdf` with the prompt currently in `scripts/vision_cost_test.py`:

**Worked correctly:**
- Q4 (dropped √): all four options have correct radicals, answer A correct.
- Q17 (stranded numerator): fractions 27/7, 10/3, 13/4, 29/9 all correct, answer D correct.
- Q18 (dropped √ in geometry): clean LaTeX, correct answer.

**Issues to fix in production prompt:**
- Q1: `["2", "$\frac{1}{2}$", "$-\frac{1}{2}$", "-2"]` — bare integers slipped past the consistency rule. Fix: add a worked example to the prompt (documented in plan).
- Q17, Q18: `sub_type` came back as `"Geometry"` instead of `"QUANT_STANDARD"` — LLM collapsed `sub_type` into `sub_topic`. Fix: lock via `Literal[QUANT_STANDARD]` in the response schema (documented in plan).

Both fixes are baked into the v2 plan.

---

## Notes for next session

- `vision_cost_test.py` stays in the repo as a diagnostic tool, not a production component. Re-run it after any prompt change to sanity-check before committing.
- Old `data/` subdirs (`raw_text/`, `parsed/`, `answer_keys/`, `enriched/`) get deleted in step 12 of migration. Snapshot any contents you want to keep (the v1 outputs may be useful for regression comparison) before deletion.
- The v1 `PROGRESS.md` is preserved as historical record — don't overwrite it. This file replaces it going forward.
