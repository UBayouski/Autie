"""Unit tests for the heading-aware chunker (no credentials needed)."""

from ingestion.chunker import MAX_CHARS, MIN_CHARS, chunk_html, chunk_jats

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


def test_reference_sections_dropped():
    html = """
    <html><body><main>
      <h2>Discussion</h2><p>{body}</p>
      <h2>References</h2><p>{refs}</p>
    </main></body></html>
    """.format(
        body="Findings suggest early intervention helps. " * 10,
        refs="1. Smith J, et al. Some paper title. J Autism. (2019). doi:10.1/x. " * 10,
    )
    sections = {c.section for c in chunk_html(html)}
    assert "Discussion" in sections
    assert "References" not in sections


JATS = """<?xml version="1.0"?>
<article>
  <front><article-meta><abstract><p>{abstract}</p></abstract></article-meta></front>
  <body>
    <sec><title>Introduction</title><p>{intro}</p>
      <sec><title>Nested Background</title><p>{nested}</p></sec>
    </sec>
    <sec><title>Methods</title><p>{methods}</p></sec>
  </body>
  <back><ref-list><ref><p>{refs}</p></ref></ref-list></back>
</article>
""".format(
    abstract="This review summarizes diagnostic tools. " * 8,
    intro="ADHD affects attention regulation across ages. " * 8,
    nested="Background detail on prevalence estimates worldwide. " * 8,
    methods="We searched databases for eligible studies. " * 8,
    refs="1. Author A. Title. Journal. (2020). doi:10.1/y. " * 10,
)


def test_jats_sections_use_sec_titles():
    sections = {c.section for c in chunk_jats(JATS)}
    assert {"Abstract", "Introduction", "Nested Background", "Methods"} <= sections


def test_jats_reference_list_dropped():
    text = " ".join(c.text for c in chunk_jats(JATS))
    assert "doi:10.1/y" not in text


def test_jats_nested_sections_not_duplicated():
    chunks = chunk_jats(JATS)
    intro = " ".join(c.text for c in chunks if c.section == "Introduction")
    assert "Background detail" not in intro


def test_long_sections_split_within_budget():
    long_html = "<html><body><main><h1>Long</h1>{}</main></body></html>".format(
        "".join(f"<p>Paragraph {i}: " + "words and more words. " * 30 + "</p>" for i in range(20))
    )
    chunks = chunk_html(long_html)
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS + 400 for c in chunks)  # small slack for overlap join
