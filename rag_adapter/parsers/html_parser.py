from bs4 import BeautifulSoup

from rag_adapter.models import Document


class HtmlParser:
    """把 HTML 去標籤,抽出純文字與 <title>。供 url / tkms 等 HTML 來源使用。"""

    def parse(self, document):
        soup = BeautifulSoup(document.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        metadata = dict(document.metadata)
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string.strip()
        return Document(
            id=document.id,
            text=text,
            metadata=metadata,
            source_ref=document.source_ref,
        )
