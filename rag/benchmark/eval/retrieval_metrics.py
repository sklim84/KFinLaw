"""
검색 메트릭 — 검색된 청크의 source_uids 와 골드셋 gold_ids 비교
recall@k, precision@k, MRR, nDCG, hit@k
"""
import math


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
    top = ranked_chunks[:k]
    hits = sum(1 for c in top if gold & set(c["source_uids"]))
    denom = len(top)  # 실제 반환 수로 나눔(parent-doc 등 k 미만 반환 시 과소평가 방지)
    return hits / denom if denom else 0.0


def mrr(ranked_chunks, gold_ids):
    gold = set(gold_ids)
    for i, c in enumerate(ranked_chunks, 1):
        if gold & set(c["source_uids"]):
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked_chunks, gold_ids, k):
    """다중 gold 대응: 각 gold id를 '최초로 등장한 순위'에서 1회만 보상(중복 제거).
    한 청크가 여러 gold를 담아도(co-location) 순위 1개로 계산되며, 1.0 상한.
    단일 gold(factoid/crossref/byeolpyo)에선 정확, 다중 gold(multihop)에선 하한 근사."""
    gold = set(gold_ids)
    dcg, seen = 0.0, set()
    for i, c in enumerate(ranked_chunks[:k], 1):
        new = (gold & set(c["source_uids"])) - seen
        if new:
            dcg += 1.0 / math.log2(i + 1)
            seen |= new
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return min(dcg / ideal, 1.0) if ideal else 0.0


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
