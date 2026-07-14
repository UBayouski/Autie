"""Heading-aware chunking for the RAG corpus.

Own script by design (docs/rag-constraints.md §5): no Vertex chunker or
Document AI. Long sections are split on paragraph boundaries to a character
budget (~500-800 tokens at ~4 chars/token) with overlap between consecutive
chunks of the same section.

Two input shapes, because the corpus has two kinds of source:
  - chunk_html: .gov pages and publisher sites (PLOS/Frontiers/BMC). Sections
    follow h1-h3 headings.
  - chunk_jats: PMC full text from the E-utilities efetch API, which is JATS
    XML — sections are <sec> with a <title>, so the HTML path would see no
    headings at all and label every chunk with the first <title>.

Both paths drop reference/bibliography sections: they are pure citation lists
that embed as noise and pollute retrieval.
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

MAX_CHARS = 2800
OVERLAP_CHARS = 300
MIN_CHARS = 120  # drop boilerplate fragments

_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]

# JATS: <back> holds refs/acknowledgements/competing interests; figures and
# tables lose their meaning as flat text.
_STRIP_TAGS_JATS = ["ref-list", "back", "fig", "table-wrap", "fn-group"]

_REF_HEADING = re.compile(
    r"^\s*(references?|bibliography|works cited|citations?|further reading|"
    r"supporting information|acknowledge?ments?|competing interests|"
    r"author contributions|funding)\b",
    re.I,
)


@dataclass
class Chunk:
    text: str
    section: str


def _sections_from_html(html: str) -> list[tuple[str, str]]:
    """Returns (section_heading, section_text) pairs in document order."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.body or soup

    sections: list[tuple[str, list[str]]] = []
    current_heading = soup.title.get_text(strip=True) if soup.title else "Introduction"
    current_parts: list[str] = []
    for el in root.find_all(["h1", "h2", "h3", "p", "li"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3"):
            if current_parts:
                sections.append((current_heading, current_parts))
            current_heading = text
            current_parts = []
        else:
            current_parts.append(text)
    if current_parts:
        sections.append((current_heading, current_parts))
    return [(heading, "\n".join(parts)) for heading, parts in sections]


def _sections_from_jats(xml: str) -> list[tuple[str, str]]:
    """Returns (section_heading, section_text) pairs from PMC JATS full text."""
    soup = BeautifulSoup(xml, "xml")
    for tag in soup(_STRIP_TAGS_JATS):
        tag.decompose()

    sections: list[tuple[str, str]] = []

    abstract = soup.find("abstract")
    if abstract:
        text = "\n".join(
            p.get_text(" ", strip=True) for p in abstract.find_all("p")
        ).strip()
        if text:
            sections.append(("Abstract", text))

    body = soup.find("body")
    if body is None:
        return sections

    for sec in body.find_all("sec"):
        title_el = sec.find("title", recursive=False)
        heading = title_el.get_text(" ", strip=True) if title_el else "Introduction"
        # Only paragraphs owned by this <sec>; nested <sec>s are visited on
        # their own turn and would otherwise be duplicated into the parent.
        parts = [
            text
            for p in sec.find_all("p")
            if p.find_parent("sec") is sec and (text := p.get_text(" ", strip=True))
        ]
        if parts:
            sections.append((heading, "\n".join(parts)))

    return sections


def _split_long(text: str) -> list[str]:
    """Splits text on paragraph boundaries into MAX_CHARS pieces with overlap."""
    if len(text) <= MAX_CHARS:
        return [text]
    paragraphs = text.split("\n")
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n{para}".strip() if current else para
        if len(candidate) > MAX_CHARS and current:
            pieces.append(current)
            current = current[-OVERLAP_CHARS:] + "\n" + para
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _to_chunks(sections: list[tuple[str, str]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, text in sections:
        if _REF_HEADING.match(heading):
            continue
        for piece in _split_long(text):
            if len(piece) >= MIN_CHARS:
                chunks.append(Chunk(text=piece, section=heading))
    return chunks


def chunk_html(html: str) -> list[Chunk]:
    return _to_chunks(_sections_from_html(html))


def chunk_jats(xml: str) -> list[Chunk]:
    return _to_chunks(_sections_from_jats(xml))
