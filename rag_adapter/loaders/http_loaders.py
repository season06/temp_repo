import httpx

from rag_adapter.models import Document, SourceRef


def _as_list(value):
    return [value] if isinstance(value, str) else list(value)


class UrlLoader:
    """以非同步 HTTP GET 抓取一或多個 URL 的原始內容(通常為 HTML),不解析。"""

    def __init__(self, client=None, loader_name="url"):
        self._client = client or httpx.AsyncClient(timeout=30)
        self._loader_name = loader_name

    async def load(self, location):
        documents = []
        for url in _as_list(location):
            response = await self._client.get(url)
            response.raise_for_status()
            ref = SourceRef(loader=self._loader_name, location=url)
            documents.append(Document(id=url, text=response.text, source_ref=ref))
        return documents


class TkmsLoader:
    """公司內部 wiki(TKMS)。目前以 HTML 處理:依 page id 組出 URL 非同步抓取。"""

    def __init__(self, base_url, client=None):
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=30)

    async def load(self, location):
        documents = []
        for page_id in _as_list(location):
            url = f"{self._base_url}/{page_id}"
            response = await self._client.get(url)
            response.raise_for_status()
            ref = SourceRef(loader="tkms", location=url)
            documents.append(Document(id=url, text=response.text, source_ref=ref))
        return documents
