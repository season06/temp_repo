# RAG Adapter — P4 Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 補上生成層:`TemplatePromptBuilder`(組 prompt,sync)與 `QwenGenerator`(OpenAI 相容 chat completions,`generate` + SSE `stream`,async),接上 `QueryPipeline.answer/stream`,並擴充 config 的 `query.generation` 區塊(預設關閉)。

**Architecture:** PromptBuilder 為 CPU 層(sync),Generator 為 I/O 層(async,`stream` 為 async generator)。QueryPipeline 既有 `answer/stream` 已支援可選 prompt_builder/generator,本階段提供真實實作並由 factory 在 `generation.enabled` 時組入。Generator 透過注入的 client 呼叫 `/chat/completions`,citations 由 pipeline 帶入、原樣回傳。

**Tech Stack:** Python 3.10+、asyncio、httpx.AsyncClient(chat + SSE streaming)、pytest + pytest-asyncio。

> 規格依據:`docs/superpowers/specs/2026-06-14-rag-adapter-design.md`
> 型別:最小註記;`config.py` 例外採 typed frozen dataclass。
> 設計取捨:system prompt 放在 Generator(chat system message);PromptBuilder 只組 user 訊息內容。

---

## File Structure

```
rag_adapter/
  prompts/
    __init__.py
    template_prompt_builder.py     # TemplatePromptBuilder
  generators/
    __init__.py
    qwen_generator.py              # QwenGenerator(generate + stream)
  config.py                        # 修改:query.generation schema
  factory.py                       # 修改:enabled 時組入 prompt_builder + generator
tests/
  test_template_prompt_builder.py
  test_qwen_generator.py
  test_config.py                   # 修改:generation 斷言
  test_factory.py                  # 修改:generation-enabled build 斷言
  test_generation_integration.py
```

---

## Task 1: 套件目錄

**Files:**
- Create: `rag_adapter/prompts/__init__.py`、`rag_adapter/generators/__init__.py`

- [ ] **Step 1:** 建立兩個空 `__init__.py`(內容空字串)。
- [ ] **Step 2: Commit**

```bash
git add rag_adapter/prompts/__init__.py rag_adapter/generators/__init__.py
git commit -m "chore: add prompts and generators package dirs"
```

---

## Task 2: TemplatePromptBuilder

**Files:**
- Create: `rag_adapter/prompts/template_prompt_builder.py`
- Test: `tests/test_template_prompt_builder.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_template_prompt_builder.py`:
```python
from rag_adapter.prompts.template_prompt_builder import TemplatePromptBuilder


def test_default_template_includes_context_and_query():
    prompt = TemplatePromptBuilder().build_prompt("what is x?", "x is a thing")

    assert "x is a thing" in prompt
    assert "what is x?" in prompt


def test_custom_template():
    builder = TemplatePromptBuilder(template="C={context} Q={query}")

    assert builder.build_prompt("q1", "c1") == "C=c1 Q=q1"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_template_prompt_builder.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 實作**

`rag_adapter/prompts/template_prompt_builder.py`:
```python
DEFAULT_TEMPLATE = (
    "請根據以下資料回答問題,並在適當處引用來源編號 [n]。\n\n"
    "資料:\n{context}\n\n"
    "問題:{query}"
)


class TemplatePromptBuilder:
    """以 template 把 context 與 query 組成 user prompt(system prompt 由 generator 處理)。"""

    def __init__(self, template=None):
        self._template = template or DEFAULT_TEMPLATE

    def build_prompt(self, query, context):
        return self._template.format(query=query, context=context)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_template_prompt_builder.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/prompts/template_prompt_builder.py tests/test_template_prompt_builder.py
git commit -m "feat: add template prompt builder"
```

---

## Task 3: QwenGenerator（chat completions + SSE streaming)

**Files:**
- Create: `rag_adapter/generators/qwen_generator.py`
- Test: `tests/test_qwen_generator.py`

說明:`generate` 呼叫 `POST {base_url}/chat/completions`(`stream:false`),取 `choices[0].message.content`。`stream` 以 `client.stream("POST", ...)` 取得 SSE,逐行解析 `data: {json}`,yield `choices[0].delta.content`,遇 `[DONE]` 結束。citations 由 pipeline 帶入並原樣回傳。

- [ ] **Step 1: 寫失敗測試**

`tests/test_qwen_generator.py`:
```python
from rag_adapter.models import Citation
from rag_adapter.generators.qwen_generator import QwenGenerator


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeStreamCtx:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *args):
        return False


class FakeHttpClient:
    def __init__(self, chat_payload=None, stream_lines=None):
        self._chat_payload = chat_payload
        self._stream_lines = stream_lines or []
        self.calls = []
        self.stream_calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self._chat_payload)

    def stream(self, method, url, headers=None, json=None):
        self.stream_calls.append({"method": method, "url": url, "json": json})
        return FakeStreamCtx(FakeStreamResponse(self._stream_lines))


async def test_generate_returns_answer_with_citations():
    client = FakeHttpClient(chat_payload={"choices": [{"message": {"content": "the answer"}}]})
    gen = QwenGenerator(
        base_url="https://api/v1/",
        api_key="k",
        model="qwen-max",
        client=client,
        system_prompt="be helpful",
    )
    citations = [Citation(chunk_id="c1")]

    answer = await gen.generate("my prompt", citations)

    assert answer.text == "the answer"
    assert [c.chunk_id for c in answer.citations] == ["c1"]
    sent = client.calls[0]
    assert sent["url"] == "https://api/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer k"
    assert sent["json"]["messages"][0] == {"role": "system", "content": "be helpful"}
    assert sent["json"]["messages"][1] == {"role": "user", "content": "my prompt"}
    assert sent["json"]["stream"] is False


async def test_generate_without_system_prompt_omits_system_message():
    client = FakeHttpClient(chat_payload={"choices": [{"message": {"content": "a"}}]})
    gen = QwenGenerator(base_url="https://api/v1", api_key="k", model="m", client=client)

    await gen.generate("p", [])

    messages = client.calls[0]["json"]["messages"]
    assert messages == [{"role": "user", "content": "p"}]


async def test_stream_yields_content_deltas():
    lines = [
        'data: {"choices": [{"delta": {"content": "Hel"}}]}',
        "",
        'data: {"choices": [{"delta": {"content": "lo"}}]}',
        "data: [DONE]",
    ]
    client = FakeHttpClient(stream_lines=lines)
    gen = QwenGenerator(base_url="https://api/v1", api_key="k", model="m", client=client)

    tokens = [token async for token in gen.stream("p", [])]

    assert tokens == ["Hel", "lo"]
    assert client.stream_calls[0]["json"]["stream"] is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/test_qwen_generator.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 實作**

`rag_adapter/generators/qwen_generator.py`:
```python
import json

import httpx

from rag_adapter.models import Answer


class QwenGenerator:
    """以 OpenAI 相容的 /chat/completions API 生成答案(Qwen 模型)。

    generate 為一次性;stream 解析 SSE 逐段回傳。citations 由呼叫端帶入、原樣附回。
    """

    def __init__(self, base_url, api_key, model, client=None, system_prompt="", temperature=0.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=120)
        self._system_prompt = system_prompt
        self._temperature = temperature

    def _messages(self, prompt):
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _headers(self):
        return {"Authorization": f"Bearer {self._api_key}"}

    def _payload(self, prompt, stream):
        return {
            "model": self._model,
            "messages": self._messages(prompt),
            "temperature": self._temperature,
            "stream": stream,
        }

    async def generate(self, prompt, citations):
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=self._payload(prompt, False),
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        return Answer(text=text, citations=list(citations))

    async def stream(self, prompt, citations):
        async with self._client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=self._payload(prompt, True),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                delta = json.loads(data)["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/test_qwen_generator.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add rag_adapter/generators/qwen_generator.py tests/test_qwen_generator.py
git commit -m "feat: add qwen chat generator with streaming"
```

---

## Task 4: config generation schema + factory wiring

**Files:**
- Modify: `rag_adapter/config.py`、`rag_adapter/factory.py`、`tests/test_config.py`、`tests/test_factory.py`

- [ ] **Step 1: config.py 新增 generation schema**

在 `QueryConfig` 定義之前插入:
```python
@dataclass(frozen=True)
class PromptBuilderConfig:
    type: str = "template"
    template: str | None = None


@dataclass(frozen=True)
class GeneratorConfig:
    type: str = "qwen"
    base_url: str = ""
    api_key: str = ""
    model: str = "qwen-max"
    temperature: float = 0.0
    system_prompt: str = ""


@dataclass(frozen=True)
class GenerationConfig:
    enabled: bool = False
    prompt_builder: PromptBuilderConfig = field(default_factory=PromptBuilderConfig)
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
```
在 `QueryConfig` 加上欄位(置於 `context` 之後、`top_k` 之前):
```python
    generation: GenerationConfig = field(default_factory=GenerationConfig)
```
在 `_query_from_dict` 中加入 generation 解析(回傳前組裝):
```python
def _generation_from_dict(raw: dict) -> GenerationConfig:
    return GenerationConfig(
        enabled=raw.get("enabled", False),
        prompt_builder=PromptBuilderConfig(**raw.get("prompt_builder", {})),
        generator=GeneratorConfig(**raw.get("generator", {})),
    )
```
並把 `_query_from_dict` 改為包含 generation:
```python
def _query_from_dict(raw: dict) -> QueryConfig:
    return QueryConfig(
        retriever=RetrieverConfig(**raw.get("retriever", {})),
        fusion=FusionConfig(**raw.get("fusion", {})),
        reranker=RerankerConfig(**raw.get("reranker", {})),
        context=ContextConfig(**raw.get("context", {})),
        generation=_generation_from_dict(raw.get("generation", {})),
        top_k=raw.get("top_k", 8),
    )
```

- [ ] **Step 2: factory.py 接上生成**

import 區補:
```python
from rag_adapter.prompts.template_prompt_builder import TemplatePromptBuilder
from rag_adapter.generators.qwen_generator import QwenGenerator
```
新增建構函式(放在 `_build_reranker` 之後):
```python
def _build_prompt_builder(config):
    if config.type == "template":
        return TemplatePromptBuilder(template=config.template)
    raise ValueError(f"unknown prompt builder type: {config.type}")


def _build_generator(config):
    if config.type == "qwen":
        return QwenGenerator(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature,
            system_prompt=config.system_prompt,
        )
    raise ValueError(f"unknown generator type: {config.type}")
```
把 `build_query_pipeline` 改為(在 enabled 時組入生成):
```python
def build_query_pipeline(config):
    """依 RagConfig 組裝 QueryPipeline。generation.enabled 時一併組入 prompt_builder + generator
    (可用 answer/stream);否則只到 retrieve_context。dense retriever 與 indexing 共用 embedder / store。
    """
    embedder = _build_embedder(config.indexing.embedder)
    vector_store = _build_vector_store(config.indexing.vector_store)
    query = config.query
    generation = query.generation
    prompt_builder = _build_prompt_builder(generation.prompt_builder) if generation.enabled else None
    generator = _build_generator(generation.generator) if generation.enabled else None
    return QueryPipeline(
        retrievers=[_build_retriever(query.retriever, embedder, vector_store)],
        fusion=_build_fusion(query.fusion),
        reranker=_build_reranker(query.reranker),
        context_builder=DefaultContextBuilder(max_chars=query.context.max_chars),
        top_k=query.top_k,
        prompt_builder=prompt_builder,
        generator=generator,
    )
```

- [ ] **Step 3: 更新 tests/test_config.py**

在 `_YAML` 的 `context:` 區塊之後、`top_k: 5` 之前插入:
```python
  generation:
    enabled: true
    prompt_builder:
      type: template
    generator:
      type: qwen
      base_url: https://api/v1
      api_key: ${ENV:QWEN_KEY}
      model: qwen-max
      temperature: 0.2
      system_prompt: be helpful
```
在 `test_load_config_returns_typed_config_with_env_interpolation` 末端追加:
```python
    assert config.query.generation.enabled is True
    assert config.query.generation.generator.api_key == "secret-123"
    assert config.query.generation.generator.temperature == 0.2
    assert config.query.generation.prompt_builder.type == "template"
```

- [ ] **Step 4: 更新 tests/test_factory.py**

把 `_YAML` 同步加入與 Step 3 相同的 `generation:` 區塊(置於 `context:` 之後、`top_k: 5` 之前),並新增測試:
```python
def test_build_query_pipeline_with_generation(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_KEY", "secret-123")
    cfg = tmp_path / "rag.yaml"
    cfg.write_text(textwrap.dedent(_YAML), encoding="utf-8")
    config = load_config(str(cfg))

    from rag_adapter.factory import build_query_pipeline
    from rag_adapter.prompts.template_prompt_builder import TemplatePromptBuilder
    from rag_adapter.generators.qwen_generator import QwenGenerator

    pipeline = build_query_pipeline(config)

    assert isinstance(pipeline._prompt_builder, TemplatePromptBuilder)
    assert isinstance(pipeline._generator, QwenGenerator)
```

- [ ] **Step 5: 跑測試**

Run: `pytest tests/test_config.py tests/test_factory.py -q`
Expected: PASS（全部 passed）

- [ ] **Step 6: Commit**

```bash
git add rag_adapter/config.py rag_adapter/factory.py tests/test_config.py tests/test_factory.py
git commit -m "feat: add generation config and wire prompt builder + generator into factory"
```

---

## Task 5: 生成整合測試 + 全套件驗證

**Files:**
- Test: `tests/test_generation_integration.py`

- [ ] **Step 1: 寫整合測試**(真實 TemplatePromptBuilder + 假 generator,經 QueryPipeline answer/stream)

`tests/test_generation_integration.py`:
```python
from rag_adapter.models import Chunk
from rag_adapter.pipeline.query import QueryPipeline
from rag_adapter.retrievers.dense_retriever import DenseRetriever
from rag_adapter.fusion.rrf_fusion import RRFFusion
from rag_adapter.context.context_builder import DefaultContextBuilder
from rag_adapter.prompts.template_prompt_builder import TemplatePromptBuilder
from rag_adapter.testing.mocks import EchoEmbedder, InMemoryVectorStore, NoopReranker, EchoGenerator


async def _pipeline():
    store = InMemoryVectorStore()
    await store.upsert([
        Chunk(id="c1", document_id="d", text="aa", embedding=[2.0]),
        Chunk(id="c2", document_id="d", text="aaaa", embedding=[4.0]),
    ])
    return QueryPipeline(
        retrievers=[DenseRetriever(EchoEmbedder(), store)],
        fusion=RRFFusion(),
        reranker=NoopReranker(),
        context_builder=DefaultContextBuilder(max_chars=1000),
        prompt_builder=TemplatePromptBuilder(),
        generator=EchoGenerator(),
        top_k=2,
    )


async def test_answer_runs_full_pipeline_with_real_prompt_builder():
    pipeline = await _pipeline()

    answer = await pipeline.answer("aaaa")

    assert answer.text.startswith("ANSWER:")
    assert "aaaa" in answer.text
    assert {c.chunk_id for c in answer.citations} == {"c1", "c2"}


async def test_stream_runs_full_pipeline():
    pipeline = await _pipeline()

    tokens = [token async for token in pipeline.stream("aaaa")]

    assert len(tokens) > 0
```

- [ ] **Step 2: 跑整合測試**

Run: `pytest tests/test_generation_integration.py -q`
Expected: PASS（2 passed）

- [ ] **Step 3: 全套件**

Run: `pytest -q`
Expected: PASS(P1–P3 既有 49 + P4 新增,全部 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_generation_integration.py
git commit -m "test: add generation integration through query pipeline"
```

---

## Self-Review

**Spec coverage:** PromptBuilder(Task 2)、Generator generate/stream(Task 3)、config-driven generation + factory(Task 4)、端到端 answer/stream(Task 5)✓
**Async 邊界:** Generator.generate/stream async(stream 為 async generator);PromptBuilder.build_prompt sync ✓
**Placeholder scan:** 無 TBD/TODO;每步皆有完整程式碼。
**一致性:** citations 由 pipeline 帶入、generator 原樣回傳;system_prompt 在 generator;factory 在 enabled 時才組入生成。

---

## 後續
- **P5 Obs + Eval**:Langfuse trace(含 generation)、Retrieval 指標離線評估。
