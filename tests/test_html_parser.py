from rag_adapter.models import Document, SourceRef
from rag_adapter.parsers.html_parser import HtmlParser


def test_html_parser_strips_tags_and_extracts_title():
    html = (
        "<html><head><title> Hi </title></head>"
        "<body><p>Hello <b>world</b></p><script>x()</script></body></html>"
    )
    doc = Document(id="d1", text=html, source_ref=SourceRef(loader="url", location="http://x"))
    out = HtmlParser().parse(doc)

    assert out.id == "d1"
    assert out.text == "Hi Hello world"
    assert out.metadata["title"] == "Hi"
    assert out.source_ref.location == "http://x"


def test_html_parser_without_title():
    doc = Document(id="d2", text="<p>just body</p>")
    out = HtmlParser().parse(doc)

    assert out.text == "just body"
    assert "title" not in out.metadata
