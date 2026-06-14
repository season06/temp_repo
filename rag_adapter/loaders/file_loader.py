from pathlib import Path

from rag_adapter.models import Document, SourceRef


class FileLoader:
    """從檔案路徑或目錄讀取原始內容(不解析)。目錄則遞迴讀取所有檔案。"""

    def __init__(self, loader_name="file"):
        self._loader_name = loader_name

    def load(self, location):
        documents = []
        for path in self._resolve(location):
            text = path.read_text(encoding="utf-8")
            ref = SourceRef(loader=self._loader_name, location=str(path))
            documents.append(Document(id=str(path), text=text, source_ref=ref))
        return documents

    def _resolve(self, location):
        path = Path(location)
        if path.is_dir():
            return sorted(p for p in path.rglob("*") if p.is_file())
        return [path]
