import json
import re
from pathlib import Path

from src.config import PARSED_DIR, ANSWER_KEYS_DIR
from src.schema import ParsedQuestion, QuestionType, QuestionSubType


PAGE_NUM_RE = re.compile(r"^\d+/\d+$")
ANSWER_ENTRY_RE = re.compile(r"(\d+)\.(\S+)")
OPTION_LINE_RE = re.compile(r"^([A-D])(?:\s+(.+))?$")
VIDEO_SOLUTION = "VIDEO SOLUTION"


def _strip_page_numbers(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if not PAGE_NUM_RE.match(line.strip())
    )


def _parse_answer_key(text: str) -> dict[int, str]:
    m = re.search(r"\bAnswers\b(.*?)\bExplanations\b", text, re.DOTALL)
    if not m:
        raise ValueError("Cannot locate 'Answers...Explanations' block")
    return {int(n): ans for n, ans in ANSWER_ENTRY_RE.findall(m.group(1))}


def _type_from_answer(ans: str) -> QuestionType:
    return QuestionType.MCQ if ans.strip().upper() in {"A", "B", "C", "D"} else QuestionType.TITA


def _find_option_block_start(lines: list[str]) -> int | None:
    """Return index of the 'A' line that begins a valid A→B→C→D block."""
    positions: dict[str, list[int]] = {"A": [], "B": [], "C": [], "D": []}
    for i, line in enumerate(lines):
        m = OPTION_LINE_RE.match(line)
        if m:
            positions[m.group(1)].append(i)

    # Prefer the latest A that has B, C, D after it in order.
    for a in reversed(positions["A"]):
        b = next((p for p in positions["B"] if p > a), None)
        if b is None: continue
        c = next((p for p in positions["C"] if p > b), None)
        if c is None: continue
        d = next((p for p in positions["D"] if p > c), None)
        if d is None: continue
        return a
    return None


def _parse_questions(
    text: str,
    section_header: str,
    types: dict[int, QuestionType],
) -> dict[int, tuple[str, list[str] | None]]:
    m = re.search(
        rf"\n{re.escape(section_header)}\n(.*?)\bAnswers\b",
        text, re.DOTALL,
    )
    if not m:
        raise ValueError(f"Cannot locate '{section_header}...Answers' block")
    body = m.group(1)

    parts = re.split(r"(?m)^(?=\d+\.\s)", body)

    result: dict[int, tuple[str, list[str] | None]] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        head = re.match(r"(\d+)\.\s*(.*)", part, re.DOTALL)
        if not head:
            continue
        qnum = int(head.group(1))
        block = head.group(2)

        lines: list[str] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if VIDEO_SOLUTION in line:
                break
            lines.append(line)

        if types.get(qnum) != QuestionType.MCQ:
            result[qnum] = (" ".join(lines).strip(), None)
            continue

        a_pos = _find_option_block_start(lines)
        if a_pos is None:
            raise ValueError(f"Q{qnum}: MCQ but no valid A→B→C→D block")

        q_text = " ".join(lines[:a_pos]).strip()

        opts: dict[str, list[str]] = {}
        cur: str | None = None
        for line in lines[a_pos:]:
            opt_m = OPTION_LINE_RE.match(line)
            if opt_m:
                cur = opt_m.group(1)
                opts.setdefault(cur, [])
                if opt_m.group(2):
                    opts[cur].append(opt_m.group(2))
            elif cur:
                opts[cur].append(line)

        options = [" ".join(opts.get(letter, [])).strip() for letter in "ABCD"]
        result[qnum] = (q_text, options)

    return result


def _parse_explanations(text: str) -> dict[int, str]:
    m = re.search(r"\bExplanations\b(.*)$", text, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)
    parts = re.split(r"(?m)^(?=\d+\.\S+\s*$)", body)
    result: dict[int, str] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        head = re.match(r"(\d+)\.(\S+)\s*\n(.*)", part, re.DOTALL)
        if not head:
            continue
        qnum = int(head.group(1))
        raw = head.group(3)
        raw = re.split(r"\s*VIDEO SOLUTION", raw)[0].strip()
        result[qnum] = raw
    return result


def parse_qa(raw_text_path: Path, source_pdf: str) -> tuple[Path, Path]:
    out_parsed = PARSED_DIR / (raw_text_path.stem + ".json")
    out_keys = ANSWER_KEYS_DIR / (raw_text_path.stem + ".json")

    if out_parsed.exists() and out_keys.exists():
        parsed = json.loads(out_parsed.read_text())
        keys = json.loads(out_keys.read_text())
        if len(parsed) == len(keys):
            return out_parsed, out_keys

    text = _strip_page_numbers(raw_text_path.read_text())

    answers = _parse_answer_key(text)
    types = {qnum: _type_from_answer(ans) for qnum, ans in answers.items()}
    questions = _parse_questions(text, "Quant", types)
    explanations = _parse_explanations(text)

    if set(answers.keys()) != set(questions.keys()):
        raise ValueError(
            f"Count mismatch in {source_pdf}: "
            f"answers={sorted(answers.keys())} questions={sorted(questions.keys())}"
        )

    blocks: list[dict] = []
    for qnum in sorted(answers.keys()):
        qtype = _type_from_answer(answers[qnum])
        q_text, options = questions[qnum]

        if qtype == QuestionType.MCQ and not options:
            raise ValueError(f"Q{qnum}: answer key says MCQ but no options parsed")
        if qtype == QuestionType.TITA and options:
            raise ValueError(f"Q{qnum}: answer key says TITA but options found: {options}")

        blocks.append(ParsedQuestion(
            question_number=qnum,
            type=qtype,
            sub_type=QuestionSubType.QUANT_STANDARD,
            shared_passage=None,
            raw_text=q_text,
            raw_options=options,
            raw_explanation=explanations.get(qnum),
            source_pdf=source_pdf,
        ).model_dump(mode="json"))

    out_parsed.write_text(json.dumps(blocks, indent=2, ensure_ascii=False))
    out_keys.write_text(json.dumps({str(k): v for k, v in answers.items()}, indent=2))

    return out_parsed, out_keys


def parse_blocks(raw_text_path: Path, source_pdf: str) -> tuple[Path, Path]:
    stem = raw_text_path.stem.lower()
    if "qa" in stem:
        return parse_qa(raw_text_path, source_pdf)
    if "varc" in stem:
        raise NotImplementedError("VARC parsing not yet implemented")
    raise ValueError(f"Cannot infer section from filename: {stem}")
