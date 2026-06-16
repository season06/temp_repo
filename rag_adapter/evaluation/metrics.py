import math


def recall_at_k(retrieved_ids, relevant_ids, k):
    """top-k 命中的相關項數 / 全部相關項數。"""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    hits = len(set(retrieved_ids[:k]) & relevant)
    return hits / len(relevant)


def precision_at_k(retrieved_ids, relevant_ids, k):
    """top-k 中相關項的比例(分母為實際取到的數量,最多 k)。"""
    top = retrieved_ids[:k]
    if not top:
        return 0.0
    hits = len(set(top) & set(relevant_ids))
    return hits / len(top)


def reciprocal_rank(retrieved_ids, relevant_ids):
    """第一個相關項的 1/排名(找不到為 0)。"""
    relevant = set(relevant_ids)
    for index, rid in enumerate(retrieved_ids):
        if rid in relevant:
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at_k(retrieved_ids, relevant_ids, k):
    """二元相關度的 nDCG@k。"""
    relevant = set(relevant_ids)
    dcg = 0.0
    for index, rid in enumerate(retrieved_ids[:k]):
        if rid in relevant:
            dcg += 1.0 / math.log2(index + 2)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0
