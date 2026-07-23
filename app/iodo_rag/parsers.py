from __future__ import annotations

import re
from pathlib import Path

import docx
from pypdf import PdfReader


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pdf(path: Path) -> tuple[str, list[dict[str, object]]]:
    reader = PdfReader(str(path))
    pages: list[dict[str, object]] = []
    parts: list[str] = []

    for index, page in enumerate(reader.pages, start=1):
        page_text = normalize_text(page.extract_text() or "")
        pages.append({"page": index, "text": page_text})
        if page_text:
            parts.append(f"\n\n[PAGE {index}]\n{page_text}")

    return normalize_text("\n".join(parts)), pages


def parse_docx(path: Path) -> tuple[str, list[dict[str, object]]]:
    document = docx.Document(str(path))
    paragraphs = []
    for paragraph in document.paragraphs:
        value = normalize_text(paragraph.text)
        if not value:
            continue
        style = paragraph.style.name if paragraph.style else ""
        match = re.match(r"(?i)^heading\s+([1-6])$", style)
        if match:
            value = f"{'#' * int(match.group(1))} {value}"
        paragraphs.append(value)
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    text = normalize_text("\n\n".join(paragraphs))
    return text, [{"paragraphs": len(paragraphs)}]


def parse_document(path: Path) -> tuple[str, list[dict[str, object]], str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, details = parse_pdf(path)
        return text, details, "application/pdf"
    if suffix == ".docx":
        text, details = parse_docx(path)
        return text, details, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    raise ValueError(f"Unsupported file type: {path.suffix}")
