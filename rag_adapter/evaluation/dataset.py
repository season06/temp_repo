from dataclasses import dataclass, field


@dataclass
class EvalCase:
    """一筆評估案例:query 與其相關(golden)chunk ids。"""
    query: str
    relevant_ids: list = field(default_factory=list)
