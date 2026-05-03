# Vision Pipeline Plan — CAT Question Extractor v2

This plan supersedes `CAT_Question_Extractor_Execution_Plan.md`. The text-only multi-stage pipeline is being retired in favour of a single vision-based Gemini call that extracts, cleans, classifies, and explains all questions in one shot.

The starting point is `scripts/vision_cost_test.py`, which already proves the approach works: 22/22 questions on `cat_2025_slot1_qa.pdf` at $0.032 and ~2.3 minutes per PDF. Q4 (dropped √ glyphs) and Q17 (stranded numerator) — both unfixable in the text-only pipeline — came back perfect.

This document describes the production pipeline built on that foundation.

---

## Why this rewrite

The old pipeline had four LLM-touching stages (text extraction, block splitting, question cleaning, explanation enrichment) plus a CSV builder. Most stages existed to work around pdfplumber's lossy 2D→1D linearisation: stacked fractions scrambled, √ glyphs dropped, ligatures replaced with null bytes, sub/superscripts flattened. Stage 3 used Gemini to repair those artefacts from text-only context.

That approach hits a wall on questions where the artefact destroys information that doesn't echo elsewhere — Q4's √ symbols got dropped from both the question and its explanation, leaving Stage 3 nothing to reconstruct from.

Vision-based extraction sidesteps the entire problem: Gemini reads the rendered PDF directly, sees what humans see, and produces final structured output without intermediate text-cleaning stages. The cost test confirmed this is both cheaper (one call replaces four) and more accurate (handles previously-impossible cases).

---

## Pipeline shape

Three stages, down from five:

1. **Extract** — Gemini reads the PDF, returns full structured output (questions, options, answer, sub_topic, explanation) in one call. Deterministic answer-key parsing happens here as a cross-check.
2. **Validate** — assert the LLM's answers match the parsed answer key, fail loudly on mismatch.
3. **Build CSV** — concatenate all extracted JSONLs, emit the bulk-upload CSV.

VARC and DILR will get their own `extract` variants later (separate prompts, separate sub_type taxonomies). This plan covers QA only.

---

## Repository layout

Strip the project to what's actually used.

**Keep:**
- `pyproject.toml`, `.env.example`, `.gitignore`
- `data/pdfs/` — input PDFs
- `data/extracted/` — per-PDF JSONL outputs from Stage 1 (renamed from `enriched/`; the term "enriched" no longer makes sense without a non-enriched precursor)
- `data/logs/` — Gemini call logs
- `data/final/` — final master CSV

**Discard:**
- `data/raw_text/`, `data/parsed/`, `data/answer_keys/`, `data/enriched/` — no intermediate stages exist
- `src/pdf_parser.py`, `src/block_splitter.py`, `src/llm_cleaner.py`, `src/explanation_processor.py` — replaced by single Stage 1 module
- `pdfplumber` dependency — Gemini handles PDFs natively
- `google-generativeai` (deprecated SDK) — `google-genai` 1.73.1 is the current one

**New:**
- `src/extractor.py` — Stage 1 (the only LLM stage)
- `src/answer_key.py` — deterministic answer-key regex parser
- `src/validator.py` — Stage 2 (cross-check)
- `src/csv_builder.py` — Stage 3 (final CSV emission)
- `src/prompts/qa.py` — QA prompt as a module-level constant, ready for VARC and DILR siblings later

`src/config.py`, `src/schema.py`, `src/gemini_client.py` — keep but rewrite. See per-module sections below.

---

## `src/schema.py`

Drop `ParsedQuestion`, `ExtractedQuestion`, `EnrichedQuestion` — there's no longer a sequence of progressive shapes. One model represents a fully-extracted question:

`Question` with fields: `question_number` (int), `category` (enum: QUANT/VARC/DILR), `type` (enum: MCQ/TITA), `sub_type` (enum, restricted to category-appropriate values via `Literal` in the per-category prompt schema — see "Schema-level enforcement" below), `text` (str, LaTeX in `$...$`), `options` (list[str] | None), `correct_answer` (str: "0"-"3" for MCQ, numeric string for TITA), `sub_topic` (str | None, from category-specific taxonomy), `explanation` (str, LaTeX, ~100 words), `source_pdf` (str).

The validator on `options` vs `type` (MCQ requires 4 options, TITA requires null) stays. It catches one whole class of LLM errors at decode time.

Drop `CSVRow.from_enriched`, replace with `CSVRow.from_question`. Logic identical, just renamed.

### Schema-level enforcement of sub_type

The cost test showed Gemini collapsing `sub_type` into `sub_topic` on Q17 and Q18 ("Geometry" instead of "QUANT_STANDARD"). The fix is structural, not prompt-based: when calling Gemini for a QA paper, the response schema sent over the wire should declare `sub_type: Literal["QUANT_STANDARD"]`. Pydantic + Gemini structured output enforces this at decode time, making the error class impossible.

Implementation pattern: `Question` in `schema.py` keeps `sub_type` as the full `QuestionSubType` enum for downstream code. The QA-specific extraction defines a private wrapper model in `src/extractor.py` with `sub_type: Literal[QuestionSubType.QUANT_STANDARD]`, used only for the Gemini call. After validation, the result is upcast to `Question`. VARC and DILR will follow the same pattern with their own Literal restrictions.

---

## `src/config.py`

Trim to what's actually referenced:

- Path constants for the surviving directories
- `GEMINI_MODEL = "gemini-2.5-flash-lite"` (keep; cost test validated this model)
- `QUANT_SUB_TOPICS` taxonomy (keep)
- `VARC_SUB_TOPICS`, `DILR_SUB_TOPICS` — keep for future use, even though VARC/DILR aren't implemented yet
- `CSV_COLUMNS` (keep)
- Drop `RATE_LIMIT_PER_MINUTE` — paid tier, no client-side limiter

Add Gemini pricing constants (`PRICE_INPUT_PER_M`, `PRICE_OUTPUT_PER_M`) so the call logger can compute per-PDF cost estimates inline. Source these from the current pricing page; document the date checked in a comment so the next reader knows when to re-verify.

---

## `src/gemini_client.py`

Rewrite to support PDF input. The current `call(prompt, schema, context)` signature assumes text-only prompts. New signature: `call(prompt, schema, pdf_bytes=None, context=None)`. When `pdf_bytes` is provided, build `contents` as `[Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt]`; otherwise pass `prompt` directly as today.

Keep the existing retry logic (3 attempts, exponential backoff on 429/500/503) and the structured logging to `data/logs/gemini_calls.jsonl`. Extend the log entry to include `pdf_size_bytes` (when applicable) and `cost_usd` (computed from token counts and the pricing constants in config). This lets you sanity-check spend without scraping the Google Cloud console.

---

## `src/prompts/qa.py`

The QA prompt lives here as a module-level constant `QA_PROMPT`. It's long enough that f-string interpolation into `extractor.py` would obscure prompt-engineering changes in git diffs — extracting it pays for itself the second time you tweak the LaTeX wrapping rules.

The prompt content is essentially the one already in `vision_cost_test.py`, with three changes informed by the cost test:

**Change 1: worked LaTeX wrapping example.** The cost test left `["2", "$\frac{1}{2}$", "$-\frac{1}{2}$", "-2"]` for Q1 — bare integers slipped through the consistency rule. Add a concrete worked example to the prompt: *"If the four options are conceptually 2, 1/2, -1/2, -2, output `["$2$", "$\frac{1}{2}$", "$-\frac{1}{2}$", "$-2$"]` — bare integers get wrapped alongside their LaTeX siblings to maintain visual consistency."* Concrete examples enforce policy more reliably than abstract rules with this model.

**Change 2: add a second worked example for non-math options.** *"If the four options are 'always true', 'sometimes true', 'never true', 'cannot be determined', leave them all unwrapped — no math notation present, no wrapping needed."* This prevents over-wrapping in the rare quant question where options are English phrases.

**Change 3: tighten the answer letter mapping rule.** Already in the cost test prompt, but worth a worked example: *"In the Answers section, '1.B' means question 1's answer is option B → output `correct_answer: "1"`. '3.6' means question 3 (TITA) has numeric answer 6 → output `correct_answer: "6"`."* Eliminates any ambiguity about the 0-indexed letter encoding.

Drop the `sub_type` instruction line entirely — that's enforced via schema now.

---

## `src/answer_key.py`

Deterministic, no LLM. Takes the same PDF (or extracted text from it) and returns `{question_number: answer_string}` — letters for MCQ, numeric strings for TITA. The regex is the one already proven in the old block_splitter: locate the `Answers...Explanations` slice, run `(\d+)\.(\S+)` over it.

Two implementation choices: (a) keep `pdfplumber` just for this one task, or (b) use `pypdf` (already a transitive dep of pdfplumber) with simpler text extraction. The Answers section is plain text — no math, no glyphs, no layout complexity — so either works. I'd go with `pypdf` to drop pdfplumber entirely, but pdfplumber is fine if you'd rather not touch dependencies.

This module exists for one reason: the answer key is the only piece of ground truth available to cross-check the LLM, so it must be parsed independently of the LLM call.

---

## `src/extractor.py`

The single Stage 1 module. Function `extract_pdf(pdf_path, force=False) -> list[Question]`:

1. **Idempotency.** If `data/extracted/<stem>.jsonl` exists and `force` is False, load and return it. No count check needed — there's no parsed file to compare against.
2. **Read PDF bytes** from disk.
3. **Build the QA-specific schema wrapper** (the one with `sub_type: Literal[QUANT_STANDARD]`).
4. **Call Gemini** via `gemini_client.call(prompt=QA_PROMPT, schema=QAExtraction, pdf_bytes=pdf_bytes, context={"stem": stem})`. `QAExtraction` wraps `list[QAQuestion]` so structured output decodes cleanly.
5. **Upcast** each `QAQuestion` to `Question` (the public schema model). This is mostly a re-validation; the field shapes match.
6. **Stamp `source_pdf`** on each question.
7. **Write JSONL** to `data/extracted/<stem>.jsonl`, one question per line.
8. **Return** the list.

No retry loop here — `gemini_client.call` already retries on transient errors. If it fails after 3 attempts, the exception propagates up and the caller sees a hard failure with the stem identified in the log entry.

No partial writes. If the call returns 21 of 22 questions, that's a hard failure (caught by the validator, see next section). The JSONL is only written after the validator passes. This means a failed run leaves no extracted file, so the next run retries from scratch — clean recovery semantics.

---

## `src/validator.py`

Function `validate(questions, answer_key, stem) -> None`. Called by `extractor.py` after the LLM call, before writing the JSONL.

Checks, all hard failures (raise on any):

- **Question count match**: `len(questions) == len(answer_key)`. If the LLM returned 21 and the answer key has 22, something's wrong — could be a missed question, could be a miscounted Answers section.
- **Question number set match**: `{q.question_number for q in questions} == set(answer_key.keys())`. Catches off-by-one errors and duplicate question numbers.
- **Answer match per question**: for each question, the LLM's `correct_answer` must agree with the parsed answer key. The encoding differs (LLM emits "0"-"3" for MCQ, key has "A"-"D"), so the validator does the mapping: MCQ key letter `L` → `str(ord(L) - ord("A"))`, TITA verbatim. Mismatch = hard fail with a clear message: *"Q4: LLM said '1', answer key says 'A' (expected '0')"*.
- **Type vs options consistency**: redundant with the Pydantic model_validator but worth a top-level check too — if MCQ has no options, or TITA has options, raise.

When a hard failure raises, the JSONL is never written, the existing extracted file (if any) is untouched, and the operator gets a stack trace pointing at the offending question. Manual fix path: edit the prompt, rerun with `--force`. Or in extreme cases, hand-edit one file with the LLM's raw output (saved to `data/logs/`) plus manual corrections, then commit it as the source of truth.

The validator runs on every extraction, even on idempotent skips — cheap and protects against data corruption from older runs that predated newer validation rules.

---

## `src/csv_builder.py`

Function `build_csv(output_path=FINAL_CSV) -> None`. Globs `data/extracted/*.jsonl`, deserialises each line into a `Question`, runs `CSVRow.from_question`, writes to the output path with `csv.writer` in `QUOTE_ALL` mode and `CSV_COLUMNS` ordering.

Dedupe by `(source_pdf, question_number)` — defensive, since two extractions of the same PDF should never produce different question sets but bugs happen. On collision, prefer the most recent file mtime.

`QUOTE_ALL` matters: option strings can contain commas (e.g. `"$(3, 10)$"`), quotes (rare but possible in word-based options), and the cost test confirmed no embedded newlines after Stage 1, but defensive quoting costs nothing.

Smoke-test the output once manually against the bulk-upload endpoint before running for real. CSV column ordering, encoding (UTF-8 with no BOM), and quoting style are all things that look right until they aren't.

Each rerun overwrites the master CSV from current extracted state. No incremental tracking — extracted JSONLs are the source of truth.

---

## Scripts

`scripts/run_one.py`: runs Stage 1 on one PDF, prints the cost summary and a sampled question. Same shape as today, simpler internals.

`scripts/run_all.py`: walks `data/pdfs/`, runs Stage 1 on each PDF that lacks an extracted output, then runs Stage 3 (CSV builder) once at the end. Stage 2 (validator) is internal to Stage 1 — no separate invocation.

`scripts/spot_check.py`: samples N random questions from `data/extracted/*.jsonl`, pretty-prints the question/options/answer/explanation for manual review. Optional flag `--with-pdf` to also open the source PDF at the question's page (useful when something looks off and you want to compare against ground truth).

`scripts/vision_cost_test.py`: keep as-is. It's the diagnostic tool for testing prompt changes against cost and accuracy. When you tweak `prompts/qa.py`, run this against a known PDF to verify nothing regressed before committing.

---

## Dependencies

`pyproject.toml` shrinks:

- Remove `pdfplumber` (unless you keep it for `answer_key.py` — see that section)
- Remove `google-generativeai` (deprecated)
- Keep `google-genai`, `pydantic`, `python-dotenv`
- Add `pypdf` if you go that route for `answer_key.py`

---

## Migration steps, in order

1. Branch off main. The text-only pipeline stays on main until v2 is validated.
2. Rewrite `schema.py` with the new `Question` model. Delete the old enriched/extracted/parsed types.
3. Rewrite `config.py` per the trim list above.
4. Rewrite `gemini_client.py` to accept optional `pdf_bytes`.
5. Create `src/prompts/qa.py` with the prompt constant. Port from `vision_cost_test.py` and apply the three changes (worked LaTeX example, non-math worked example, answer-letter worked example).
6. Create `src/answer_key.py`.
7. Create `src/validator.py`.
8. Create `src/extractor.py`.
9. Create `src/csv_builder.py`.
10. Update `scripts/run_one.py`, `scripts/run_all.py`. Add `scripts/spot_check.py`.
11. Delete the old stage modules (`pdf_parser.py`, `block_splitter.py`, `llm_cleaner.py`, `explanation_processor.py`).
12. Delete the old `data/` subdirs (`raw_text/`, `parsed/`, `answer_keys/`, `enriched/`).
13. Run `vision_cost_test.py` once on `cat_2025_slot1_qa.pdf` with the updated prompt. Verify Q1 wraps `["$2$", "$\frac{1}{2}$", "$-\frac{1}{2}$", "$-2$"]`, Q4 and Q17 stay correct, sub_type is locked to `QUANT_STANDARD` for all 22.
14. Run `scripts/run_one.py` on the same PDF through the real pipeline. Verify validator passes, JSONL written, CSV builder runs clean.
15. Hand-audit the extracted JSONL against the PDF for any drift. The cost test was preliminary — this is the actual production output.
16. Run on a second and third PDF (CAT 2024, CAT 2023) to confirm robustness across papers.
17. Smoke-test one CSV row through the bulk-upload endpoint.
18. Merge to main.

---

## Deferred work

**VARC.** Same one-shot pattern. New module `src/prompts/varc.py` with VARC prompt; new schema variants for sub_type Literals (`VARC_RC`, `VARC_JUMBLE`, etc.); RC passage handling via the existing `[PASSAGE]` / `[QUESTION]` markers in `text`. The extractor.py logic generalises with a category dispatch — `extract_pdf` infers category from filename or accepts it as a parameter, picks the right prompt and schema. Plan this when a VARC PDF is in hand.

**DILR.** Same shape as VARC — sets of related questions sharing a common setup (data table, logical puzzle). The shared-setup field is structurally identical to RC's shared passage. Plan this when a DILR PDF is in hand.

**Image-based questions.** Some quant questions reference figures (geometry diagrams, graphs). The cost test didn't surface any in `cat_2025_slot1_qa.pdf` — Q18 has a circle diagram in the source but the LLM reconstructed correct geometry from text alone. If a future PDF has figure-dependent questions where the LLM fails, the fix is prompt-side: instruct the LLM to describe figures in the question text using natural language, since the downstream renderer probably can't display them anyway. This is a "wait and see" item.

**Spot-check tooling.** The `spot_check.py` script described above is minimal. A nicer version would render the source PDF page side-by-side with the extracted JSON in HTML, making manual verification a scroll instead of a window-juggle. Worth building once the volume of extractions justifies it.

---

## Risks and mitigations

**LLM non-determinism.** Two runs of the same PDF may produce slightly different output (different LaTeX phrasings, different explanation wording). Mitigation: the validator catches semantic differences (wrong answer, wrong question count); cosmetic differences are acceptable. Don't try to enforce bit-for-bit reproducibility — that's not what this tool is for.

**Pricing changes.** Gemini's per-token rates are not stable. Mitigation: pricing constants live in `config.py` with a "last verified on YYYY-MM-DD" comment. Re-check quarterly or before a large batch run.

**PDFs that exceed Gemini's input limit.** `gemini-2.5-flash-lite` accepts large PDFs but there's a cap. Mitigation: log `pdf_size_bytes` in every call; if a PDF is rejected, the fallback is to split it (e.g. extract the Quant section pages only) and concatenate results. Not implemented now because no current PDF approaches the limit.

**Answer key parse failure.** If a Cracku PDF restructures the Answers section (different heading, different separator), the regex breaks and the validator can't run. Mitigation: `answer_key.py` raises a clear error on parse failure, naming the slice it tried to parse. Fix is a regex tweak, fast.

**Hallucinated questions.** The LLM could fabricate a 23rd question. Mitigation: the count-match check in the validator catches this immediately.
