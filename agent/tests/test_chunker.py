"""Unit tests for the heading-aware chunker (no credentials needed)."""

from ingestion.chunker import MAX_CHARS, MIN_CHARS, chunk_html

HTML = """
<html><head><title>Test Page</title></head><body>
<nav><p>Menu item that should be stripped from output entirely</p></nav>
<main>
  <h1>Autism Overview</h1>
  <p>{intro}</p>
  <h2>Signs</h2>
  <p>{signs}</p>
  <ul><li>{item1}</li><li>{item2}</li></ul>
  <h2>Tiny</h2>
  <p>short</p>
</main>
<footer><p>Footer junk that should also be stripped from output</p></footer>
</body></html>
""".format(
    intro="Autism is a developmental condition. " * 20,
    signs="Signs can include differences in communication. " * 20,
    item1="Repetitive behaviors are one possible sign to discuss. " * 3,
    item2="Strong specific interests are another possible sign here. " * 3,
)


def test_sections_follow_headings():
    chunks = chunk_html(HTML)
    sections = {c.section for c in chunks}
    assert "Autism Overview" in sections
    assert "Signs" in sections


def test_nav_and_footer_stripped():
    chunks = chunk_html(HTML)
    text = " ".join(c.text for c in chunks)
    assert "Menu item" not in text
    assert "Footer junk" not in text


def test_tiny_fragments_dropped():
    chunks = chunk_html(HTML)
    assert all(len(c.text) >= MIN_CHARS for c in chunks)
    assert not any(c.section == "Tiny" for c in chunks)


def test_long_sections_split_within_budget():
    long_html = "<html><body><main><h1>Long</h1>{}</main></body></html>".format(
        "".join(f"<p>Paragraph {i}: " + "words and more words. " * 30 + "</p>" for i in range(20))
    )
    chunks = chunk_html(long_html)
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS + 400 for c in chunks)  # small slack for overlap join
