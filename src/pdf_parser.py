import pdfplumber
from pathlib import Path
from src.config import RAW_TEXT_DIR


def parse_pdf(pdf_path: Path) -> Path:
    out_path = RAW_TEXT_DIR / (pdf_path.stem + ".txt")

    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3)
            if text:
                pages.append(text)

    out_path.write_text("\n\n".join(pages), encoding="utf-8")
    return out_path
