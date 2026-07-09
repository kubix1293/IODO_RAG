from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Regexy strukturalne
# ---------------------------------------------------------------------------

ARTICLE_RE = re.compile(r"(?im)^\s*Art\.\s*(?P<article>\d+[a-zA-Z]?)\.?")
SECTION_RE = re.compile(
    r"(?im)^\s*(?P<section>Rozdzia[lł]\s+\d+[a-zA-Z]?|DZIA[LŁ]\s+[IVXLCDM]+|§\s*\d+[a-zA-Z]?)"
)
# Ustęp: linia zaczynająca się od "1.", "2a." itd. (ale NIE "Art. 5.")
PARAGRAPH_RE = re.compile(r"(?im)^\s*(?P<paragraph>\d+[a-zA-Z]?)\.\s+")
# Punkt: "1)", "2a)", "a)", "pkt 3)"
POINT_RE = re.compile(
    r"(?im)^\s*(?P<point>\d+[a-zA-Z]?\)|[a-z]\)|pkt\s+\d+[a-zA-Z]?\))\s*"
)
MD_HEADER_RE = re.compile(r"(?m)^(?P<hashes>#{1,6})\s+(?P<title>.+)")
PAGE_RE = re.compile(r"\[PAGE (?P<page>\d+)\]")


# ---------------------------------------------------------------------------
# Model bloku
# ---------------------------------------------------------------------------

@dataclass
class Block:
    text: str
    section: str | None = None
    article: str | None = None
    paragraph: str | None = None
    point: str | None = None
    heading_path: list[str] = field(default_factory=list)  # dla markdown/prozy


def _extract_pages(text: str) -> tuple[int | None, int | None]:
    matches = list(PAGE_RE.finditer(text))
    if not matches:
        return None, None
    return int(matches[0].group("page")), int(matches[-1].group("page"))


def detect_document_type(text: str) -> str:
    """Rozpoznaje typ dokumentu, żeby dobrać strategię podziału."""
    if ARTICLE_RE.search(text) or SECTION_RE.search(text):
        return "legal"
    if MD_HEADER_RE.search(text):
        return "markdown"
    return "prose"


# ---------------------------------------------------------------------------
# 1) Dokumenty prawne: Sekcja -> Artykuł -> Ustęp -> Punkt
# ---------------------------------------------------------------------------

def _split_legal_blocks(text: str) -> list[Block]:
    lines = text.splitlines()
    blocks: list[Block] = []

    current_lines: list[str] = []
    cur_section: str | None = None
    cur_article: str | None = None
    cur_paragraph: str | None = None
    cur_point: str | None = None

    def flush():
        if current_lines:
            blocks.append(
                Block(
                    text="\n".join(current_lines).strip(),
                    section=cur_section,
                    article=cur_article,
                    paragraph=cur_paragraph,
                    point=cur_point,
                )
            )
            current_lines.clear()

    for line in lines:
        section_m = SECTION_RE.match(line)
        article_m = ARTICLE_RE.match(line)
        paragraph_m = PARAGRAPH_RE.match(line)
        point_m = POINT_RE.match(line)

        # Granica najwyższego rzędu: nowa sekcja lub artykuł -> zawsze nowy blok
        if (section_m or article_m) and current_lines:
            flush()
            cur_paragraph = None
            cur_point = None

        if section_m:
            cur_section = section_m.group("section").strip()
        if article_m:
            cur_article = article_m.group("article")
        if paragraph_m and not article_m:
            cur_paragraph = paragraph_m.group("paragraph")
            cur_point = None
        if point_m and not article_m and not paragraph_m:
            cur_point = point_m.group("point")

        current_lines.append(line)

    flush()
    return [b for b in blocks if b.text]


def _split_paragraph_level(block: Block, target_chars: int) -> list[Block]:
    """Fallback: jeśli blok artykułu jest za duży, dziel go po ustępach/punktach."""
    if len(block.text) <= target_chars:
        return [block]

    lines = block.text.splitlines()
    sub_blocks: list[Block] = []
    current_lines: list[str] = []
    cur_paragraph = block.paragraph
    cur_point = block.point

    def flush():
        if current_lines:
            sub_blocks.append(
                Block(
                    text="\n".join(current_lines).strip(),
                    section=block.section,
                    article=block.article,
                    paragraph=cur_paragraph,
                    point=cur_point,
                )
            )
            current_lines.clear()

    for line in lines:
        paragraph_m = PARAGRAPH_RE.match(line)
        point_m = POINT_RE.match(line)
        if (paragraph_m or point_m) and current_lines:
            flush()
        if paragraph_m:
            cur_paragraph = paragraph_m.group("paragraph")
            cur_point = None
        elif point_m:
            cur_point = point_m.group("point")
        current_lines.append(line)

    flush()
    return sub_blocks if sub_blocks else [block]


# ---------------------------------------------------------------------------
# 2) Markdown: nagłówki H1..H6 jako breadcrumb
# ---------------------------------------------------------------------------

def _split_markdown_blocks(text: str) -> list[Block]:
    lines = text.splitlines()
    blocks: list[Block] = []
    current_lines: list[str] = []
    heading_stack: list[tuple[int, str]] = []  # (poziom, tytuł)

    def flush():
        if current_lines:
            blocks.append(
                Block(
                    text="\n".join(current_lines).strip(),
                    heading_path=[t for _, t in heading_stack],
                )
            )
            current_lines.clear()

    for line in lines:
        header_m = MD_HEADER_RE.match(line)
        if header_m:
            flush()
            level = len(header_m.group("hashes"))
            title = header_m.group("title").strip()
            heading_stack = [h for h in heading_stack if h[0] < level]
            heading_stack.append((level, title))
        current_lines.append(line)

    flush()
    return [b for b in blocks if b.text]


# ---------------------------------------------------------------------------
# 3) Proza: akapity, z rekurencyjnym fallbackiem po zdaniach/słowach
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _recursive_split(text: str, target_chars: int) -> list[str]:
    """Rekurencyjny split w stylu LangChain RecursiveCharacterTextSplitter."""
    if len(text) <= target_chars:
        return [text] if text.strip() else []

    for separator, splitter in (
        ("\n\n", lambda t: t.split("\n\n")),
        ("\n", lambda t: t.split("\n")),
        (". ", lambda t: _SENTENCE_SPLIT_RE.split(t)),
        (" ", lambda t: t.split(" ")),
    ):
        parts = [p for p in splitter(text) if p.strip()]
        if len(parts) <= 1:
            continue
        result: list[str] = []
        buf = ""
        for part in parts:
            candidate = f"{buf} {part}".strip() if buf else part
            if len(candidate) > target_chars and buf:
                result.extend(_recursive_split(buf, target_chars))
                buf = part
            else:
                buf = candidate
        if buf:
            result.extend(_recursive_split(buf, target_chars))
        return result

    # Nic się już nie da podzielić sensownie (jedno długie "słowo") -> tnij twardo
    return [text[i:i + target_chars] for i in range(0, len(text), target_chars)]


def _split_prose_blocks(text: str, target_chars: int) -> list[Block]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    blocks: list[Block] = []
    for paragraph in paragraphs:
        for piece in _recursive_split(paragraph, target_chars):
            blocks.append(Block(text=piece))
    return blocks


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------

def split_into_chunks(
    text: str, *, target_chars: int, overlap_chars: int
) -> list[dict[str, object]]:
    doc_type = detect_document_type(text)

    if doc_type == "legal":
        blocks = _split_legal_blocks(text)
        expanded: list[Block] = []
        for b in blocks:
            expanded.extend(_split_paragraph_level(b, target_chars))
        blocks = expanded
    elif doc_type == "markdown":
        blocks = _split_markdown_blocks(text)
        # jeśli sekcja pod nagłówkiem i tak jest za duża, doetnij rekurencyjnie
        expanded = []
        for b in blocks:
            if len(b.text) <= target_chars:
                expanded.append(b)
            else:
                for piece in _recursive_split(b.text, target_chars):
                    expanded.append(Block(text=piece, heading_path=b.heading_path))
        blocks = expanded
    else:
        blocks = _split_prose_blocks(text, target_chars)

    return _merge_blocks_into_chunks(blocks, target_chars=target_chars, overlap_chars=overlap_chars)


def _merge_blocks_into_chunks(
    blocks: list[Block], *, target_chars: int, overlap_chars: int
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    buffer_blocks: list[Block] = []
    buffer_len = 0

    def flush():
        nonlocal buffer_blocks, buffer_len
        if not buffer_blocks:
            return
        chunks.append(_build_chunk(buffer_blocks))
        # overlap: zachowaj ostatnie N znaków jako punkt startowy następnego chunku,
        # ale w postaci pełnego bloku (z jego metadanymi), nie ucięte w połowie zdania
        if overlap_chars > 0 and buffer_blocks:
            tail = buffer_blocks[-1]
            if len(tail.text) <= overlap_chars:
                buffer_blocks = [tail]
                buffer_len = len(tail.text)
            else:
                buffer_blocks = []
                buffer_len = 0
        else:
            buffer_blocks = []
            buffer_len = 0

    for block in blocks:
        block_len = len(block.text)
        if buffer_len + block_len > target_chars and buffer_blocks:
            flush()
        buffer_blocks.append(block)
        buffer_len += block_len + 2  # z grubsza uwzględnij separator "\n\n"

    flush()
    return chunks


def _build_chunk(blocks: list[Block]) -> dict[str, object]:
    raw_text = "\n\n".join(b.text for b in blocks)
    clean_text = PAGE_RE.sub("", raw_text).strip()

    page_froms: list[int] = []
    page_tos: list[int] = []
    for b in blocks:
        pf, pt = _extract_pages(b.text)
        if pf is not None:
            page_froms.append(pf)
        if pt is not None:
            page_tos.append(pt)

    # metadane: bierzemy z pierwszego bloku, który ma dane pole ustawione
    def first_attr(name: str) -> str | None:
        for b in blocks:
            value = getattr(b, name)
            if value:
                return value
        return None

    heading_path: list[str] = next((b.heading_path for b in blocks if b.heading_path), [])

    return {
        "text": clean_text,
        "title": _guess_title(clean_text, heading_path),
        "section": first_attr("section"),
        "article": first_attr("article"),
        "paragraph": first_attr("paragraph"),
        "point": first_attr("point"),
        "page_from": min(page_froms) if page_froms else None,
        "page_to": max(page_tos) if page_tos else None,
        "metadata": {"heading_path": heading_path} if heading_path else {},
    }


def _guess_title(text: str, heading_path: list[str]) -> str | None:
    if heading_path:
        return heading_path[-1][:240]
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 8 and not line.startswith("Art."):
            return line[:240]
    return None
