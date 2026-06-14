from rag_adapter.models import Document
from rag_adapter.parsers.structured_parsers import JsonParser, XmlParser


def test_json_parser_collects_string_values_recursively():
    doc = Document(
        id="d1",
        text='{"title": "Hello", "meta": {"author": "amy"}, "tags": ["a", "b"], "n": 3}',
    )
    out = JsonParser().parse(doc)

    assert out.text == "Hello\namy\na\nb"
    assert out.id == "d1"


def test_xml_parser_collects_text_nodes():
    doc = Document(
        id="d2",
        text="<doc><title>Hello</title><body>world <b>here</b></body></doc>",
    )
    out = XmlParser().parse(doc)

    assert out.text == "Hello\nworld\nhere"
