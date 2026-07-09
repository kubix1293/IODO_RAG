from __future__ import annotations

import re


ARTICLE_RE = re.compile(r"(?im)^\s*Art\.\s*(?P<article>\d+[a-zA-Z]?)\.?")
SECTION_RE = re.compile(r"(?im)^\s*(Rozdzia[lł]\s+\d+[a-zA-Z]?|DZIA[LŁ]\s+[IVXLCDM]+|§\s*\d+[a-zA-Z]?)")
PARAGRAPH_RE = re.compile(r"(?im)^\s*(?P<paragraph>\d+[a-zA-Z]?)\.\s+")
PAGE_RE = re.compile(r"\[PAGE (?P<page>\d+)\]")


def _current_page(text: str) -> int | None:
    matches = list(PAGE_RE.finditer(text))
    if not matches:
        return None
    return int(matches[-1].group("page"))


def split_into_chunks(text: str, *, target_chars: int, overlap_chars: int) -> list[dict[str, object]]:
    blocks = _split_structural_blocks(text)
    chunks: list[dict[str, object]] = []
    current = ""
    metadata: dict[str, object] = {}

    for block in blocks:
        block_meta = _extract_metadata(block)
        if len(current) + len(block) > target_chars and current:
            chunks.append(_build_chunk(current, metadata))
            current = current[-overlap_chars:] if overlap_chars > 0 else ""
            metadata = {}

        current = f"{current}\n\n{block}".strip()
        metadata.update({key: value for key, value in block_meta.items() if value})

    if current:
        chunks.append(_build_chunk(current, metadata))

    return chunks


def _split_structural_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    current: list[str] = []

    for line in lines:
        is_boundary = bool(ARTICLE_RE.match(line) or SECTION_RE.match(line))
        if is_boundary and current:
            blocks.append("\n".join(current).strip())
            current = []
        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    fallback: list[str] = []
    for block in blocks:
        if len(block) <= 6000:
            fallback.append(block)
            continue
        paragraphs = [item.strip() for item in block.split("\n\n") if item.strip()]
        fallback.extend(paragraphs)
    return [block for block in fallback if block]


def _extract_metadata(text: str) -> dict[str, object]:
    article = ARTICLE_RE.search(text)
    section = SECTION_RE.search(text)
    paragraph = PARAGRAPH_RE.search(text)
    page = _current_page(text)
    return {
        "section": section.group(1) if section else None,
        "article": article.group("article") if article else None,
        "paragraph": paragraph.group("paragraph") if paragraph else None,
        "page_from": page,
        "page_to": page,
    }


def _build_chunk(text: str, metadata: dict[str, object]) -> dict[str, object]:
    clean_text = PAGE_RE.sub("", text).strip()
    title = _guess_title(clean_text)
    return {
        "text": clean_text,
        "title": title,
        "section": metadata.get("section"),
        "article": metadata.get("article"),
        "paragraph": metadata.get("paragraph"),
        "point": None,
        "page_from": metadata.get("page_from"),
        "page_to": metadata.get("page_to"),
        "metadata": {},
    }


def _guess_title(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 8 and not line.startswith("Art."):
            return line[:240]
    return None
