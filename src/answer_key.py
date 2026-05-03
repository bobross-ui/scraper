import re

import pdfplumber

_ANSWER_ENTRY_RE = re.compile(r"(\d+)\.(\S+)")


def parse(pdf_path) -> dict[int, str]:
    """Return {question_number: answer_string} parsed from the Answers section.

    answer_string is a letter (A-D) for MCQ or a numeric string for TITA.
    Raises ValueError if the Answers...Explanations block can't be found.
    """
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    m = re.search(r"\bAnswers\b(.*?)\bExplanations\b", text, re.DOTALL)
    if not m:
        raise ValueError(
            f"Cannot locate 'Answers...Explanations' block in {pdf_path}. "
            "Check that the PDF has both headings and update the regex if the format changed."
        )

    entries = _ANSWER_ENTRY_RE.findall(m.group(1))
    if not entries:
        raise ValueError(
            f"Found the Answers block in {pdf_path} but no entries matched '\\d+.\\S+'. "
            f"Slice was: {m.group(1)[:200]!r}"
        )

    return {int(n): ans for n, ans in entries}
