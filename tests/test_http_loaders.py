from rag_adapter.loaders.http_loaders import UrlLoader, TkmsLoader


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeHttpClient:
    def __init__(self, mapping):
        self._mapping = mapping
        self.requested = []

    async def get(self, url):
        self.requested.append(url)
        return FakeResponse(self._mapping[url])


async def test_url_loader_fetches_multiple_urls():
    client = FakeHttpClient({
        "http://a": "<p>A</p>",
        "http://b": "<p>B</p>",
    })
    docs = await UrlLoader(client=client).load(["http://a", "http://b"])

    assert [d.text for d in docs] == ["<p>A</p>", "<p>B</p>"]
    assert docs[0].id == "http://a"
    assert docs[0].source_ref.loader == "url"


async def test_tkms_loader_builds_page_urls():
    client = FakeHttpClient({"https://wiki/pages/42": "<p>wiki</p>"})
    docs = await TkmsLoader(base_url="https://wiki/pages/", client=client).load("42")

    assert client.requested == ["https://wiki/pages/42"]
    assert docs[0].text == "<p>wiki</p>"
    assert docs[0].source_ref.loader == "tkms"
    assert docs[0].source_ref.location == "https://wiki/pages/42"
