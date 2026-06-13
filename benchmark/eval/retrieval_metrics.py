"""
검색 메트릭 — 검색된 청크의 source_uids 와 골드셋 gold_ids 비교
recall@k, precision@k, MRR, nDCG, hit@k
"""
import math


def _retrieved_uids(ranked_chunks):
    """순위대로 각 청크의 source_uids 집합 리스트"""
    return [set(c["source_uids"]) for c in ranked_chunks]


def hit_at_k(ranked_chunks, gold_ids, k):
    gold = set(gold_ids)
    for c in ranked_chunks[:k]:
        if gold & set(c["source_uids"]):
            return 1.0
    return 0.0


def recall_at_k(ranked_chunks, gold_ids, k):
    gold = set(gold_ids)
    if not gold:
        return 0.0
    found = set()
    for c in ranked_chunks[:k]:
        found |= (gold & set(c["source_uids"]))
    return len(found) / len(gold)


def precision_at_k(ranked_chunks, gold_ids, k):
    gold = set(gold_ids)
    hits = sum(1 for c in ranked_chunks[:k] if gold & set(c["source_uids"]))
    return hits / k


def mrr(ranked_chunks, gold_ids):
    gold = set(gold_ids)
    for i, c in enumerate(ranked_chunks, 1):
        if gold & set(c["source_uids"]):
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked_chunks, gold_ids, k):
    gold = set(gold_ids)
    dcg = 0.0
    for i, c in enumerate(ranked_chunks[:k], 1):
        rel = 1.0 if (gold & set(c["source_uids"])) else 0.0
        dcg += rel / math.log2(i + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0


def evaluate(ranked_chunks, gold_ids, ks=(1, 3, 5, 10)):
    out = {}
    for k in ks:
        out[f"hit@{k}"] = hit_at_k(ranked_chunks, gold_ids, k)
        out[f"recall@{k}"] = recall_at_k(ranked_chunks, gold_ids, k)
        out[f"ndcg@{k}"] = ndcg_at_k(ranked_chunks, gold_ids, k)
    out["mrr"] = mrr(ranked_chunks, gold_ids)
    return out


def aggregate(per_q):
    """질문별 메트릭 dict 리스트 → 평균"""
    if not per_q:
        return {}
    keys = per_q[0].keys()
    return {k: sum(d[k] for d in per_q) / len(per_q) for k in keys}
