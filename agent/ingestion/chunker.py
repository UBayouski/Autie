"""Heading-aware HTML chunking for the RAG corpus.

Own script by design (docs/rag-constraints.md §5): no Vertex chunker or
Document AI. Sections follow h1-h3 headings; long sections are split on
paragraph boundaries to a character budget (~500-800 tokens at ~4 chars/token)
with overlap between consecutive chunks of the same section.
"""

from dataclasses import dataclass

from bs4 import BeautifulSoup

MAX_CHARS = 2800
OVERLAP_CHARS = 300
MIN_CHARS = 120  # drop boilerplate fragments

_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]


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


def chunk_html(html: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, text in _sections_from_html(html):
        for piece in _split_long(text):
            if len(piece) >= MIN_CHARS:
                chunks.append(Chunk(text=piece, section=heading))
    return chunks
