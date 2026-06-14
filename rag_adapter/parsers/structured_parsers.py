import json
import xml.etree.ElementTree as ET

from rag_adapter.models import Document


class JsonParser:
    """遞迴取出 JSON 中所有字串值,以換行串接為文字。"""

    def parse(self, document):
        parts = []
        self._collect(json.loads(document.text), parts)
        return Document(
            id=document.id,
            text="\n".join(parts),
            metadata=dict(document.metadata),
            source_ref=document.source_ref,
        )

    def _collect(self, node, parts):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                self._collect(value, parts)
        elif isinstance(node, list):
            for item in node:
                self._collect(item, parts)


class XmlParser:
    """取出 XML 所有文字節點,以換行串接。"""

    def parse(self, document):
        root = ET.fromstring(document.text)
        parts = [t.strip() for t in root.itertext() if t and t.strip()]
        return Document(
            id=document.id,
            text="\n".join(parts),
            metadata=dict(document.metadata),
            source_ref=document.source_ref,
        )
