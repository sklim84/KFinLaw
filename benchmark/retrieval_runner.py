"""
레이어1 검색 평가 러너 — config(파서·청커·임베더·검색기) 1개 = 1 실험
청킹 → 인덱싱 → 골드셋 질의 → 검색 메트릭(retrieval_metrics) → 결과 JSON + 리포트 표.
레이어2 답변 평가는 answer_runner.py (쌍 구조: retrieval_* ↔ answer_*).

사용:
  python benchmark/retrieval_runner.py --chunker article --retriever bm25 --byeolpyo md
  python benchmark/retrieval_runner.py --chunker article --retriever hybrid --rerank --embedder kure-v1 --byeolpyo md
"""
import sys
import json
import argparse
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "pipeline"))
sys.path.insert(0, str(HERE / "eval"))

from chunkers import build_chunks, chunk_article  # noqa: E402
from retrievers import build_retriever, ParentDocRetriever  # noqa: E402
import retrieval_metrics as RM               # noqa: E402
from common import CONFIG, load_json, load_jsonl  # noqa: E402

CORPUS = load_json(HERE / "corpus_ids.json")
load_goldset = load_jsonl


def run_one(chunker, retriever_kind, embedder_name, goldset, top_k=10, byeolpyo=None,
            rerank=False, hype=False):
    t0 = time.time()
    chunks = build_chunks(chunker, CORPUS, byeolpyo=byeolpyo)
    t_chunk = time.time() - t0

    embedder = None
    if retriever_kind in ("vector", "hybrid") or hype:
        from embedders import Embedder
        embedder = Embedder(embedder_name)

    t1 = time.time()
    if hype:
        # HyPE: 가설질문 임베딩 색인. hype=="raw"면 원문 병행(coverage gap 완화)
        from retrievers import HyPERetriever
        hq = json.load(open(HERE / "hype_cache.json", encoding="utf-8"))
        retr = HyPERetriever(chunks, embedder, hq, top_k=top_k,
                             include_raw=(hype == "raw"))
    elif chunker == "parent":
        # 자식(항)으로 검색 → 부모(조)로 dedup → 부모 전체 본문 반환
        parent_text = {c["source_uids"][0]: c["text"] for c in chunk_article(CORPUS)}
        retr = ParentDocRetriever(chunks, parent_text, retriever_kind,
                                  embedder=embedder, top_k=top_k)
    else:
        retr = build_retriever(retriever_kind, chunks, embedder=embedder, top_k=top_k)
    if rerank:
        from retrievers import Reranker
        retr = Reranker(retr, top_k=top_k)  # 기저 검색 후보를 크로스인코더로 재정렬
    t_index = time.time() - t1

    per_q, per_type, per_reg = [], defaultdict(list), defaultdict(list)
    t2 = time.time()
    for q in goldset:
        hits = retr.search(q["question"], top_k=top_k)
        ranked = [c for c, _ in hits]
        m = RM.evaluate(ranked, q["gold_ids"])
        per_q.append(m)
        per_type[q["type"]].append(m)
        per_reg[q.get("register", "formal")].append(m)  # 격식/구어 분해(HyPE 어휘격차 측정)
    t_query = time.time() - t2

    result = {
        "config": {"chunker": chunker, "retriever": retriever_kind, "embedder": embedder_name,
                   "byeolpyo": byeolpyo, "rerank": rerank},
        "n_chunks": len(chunks), "n_questions": len(goldset),
        "overall": RM.aggregate(per_q),
        "by_type": {t: RM.aggregate(v) for t, v in per_type.items()},
        "by_register": {r: RM.aggregate(v) for r, v in per_reg.items()},
        "timing": {"chunk_s": round(t_chunk, 2), "index_s": round(t_index, 2),
                   "query_s": round(t_query, 2), "q_per_s": round(len(goldset) / t_query, 1) if t_query else 0},
    }
    return result


def print_report(result):
    cfg = result["config"]
    print(f"\n{'='*70}")
    print(f"config: chunker={cfg['chunker']} | retriever={cfg['retriever']}"
          + (f" | embedder={cfg['embedder']}" if cfg['retriever'] == 'vector' else ""))
    print(f"청크 {result['n_chunks']} | 질문 {result['n_questions']} | "
          f"인덱싱 {result['timing']['index_s']}s | 질의 {result['timing']['q_per_s']}q/s")
    print("-"*70)
    o = result["overall"]
    print(f"  전체  recall@1={o['recall@1']:.3f} @3={o['recall@3']:.3f} @5={o['recall@5']:.3f} "
          f"@10={o['recall@10']:.3f} | mrr={o['mrr']:.3f} | ndcg@10={o['ndcg@10']:.3f}")
    for t, m in result["by_type"].items():
        print(f"  {t:9s} recall@5={m['recall@5']:.3f} | mrr={m['mrr']:.3f} | ndcg@10={m['ndcg@10']:.3f}")
    reg = result.get("by_register", {})
    if len(reg) > 1:  # 격식/구어 둘 다 있을 때만 (HyPE 어휘격차 비교)
        for r, m in reg.items():
            print(f"  [{r:10s}] recall@5={m['recall@5']:.3f} | mrr={m['mrr']:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunker", default="article")
    ap.add_argument("--retriever", default="bm25", choices=["bm25", "vector", "hybrid"])
    ap.add_argument("--embedder", default="kure-v1")
    ap.add_argument("--rerank", action="store_true", help="크로스인코더(bge-reranker-v2-m3) 재순위")
    ap.add_argument("--hype", nargs="?", const="questions", default=None,
                    choices=["questions", "raw"],
                    help="HyPE 색인: questions=가설질문만 / raw=가설질문+원문 병행")
    ap.add_argument("--byeolpyo", default=None, choices=[None, "md", "plain"],
                    help="별표 청크 포함 여부/소스 (byeolpyo 유형 질문 평가 시 필요)")
    ap.add_argument("--goldset", default=str(HERE / "goldset" / "questions.jsonl"))
    ap.add_argument("--top-k", type=int, default=CONFIG["retrieval"]["top_k"])
    ap.add_argument("--out", default=str(HERE / "reports"))
    args = ap.parse_args()

    goldset = load_goldset(args.goldset)
    print(f"골드셋: {len(goldset)}문 ({args.goldset})")
    result = run_one(args.chunker, args.retriever, args.embedder, goldset, args.top_k,
                     args.byeolpyo, args.rerank, args.hype)
    print_report(result)

    Path(args.out).mkdir(parents=True, exist_ok=True)
    tag = (f"{args.chunker}_{args.retriever}"
           + (f"_{args.embedder}" if args.retriever in ("vector", "hybrid") or args.hype else "")
           + ("_hype" if args.hype else "") + ("_rerank" if args.rerank else ""))
    fp = Path(args.out) / f"{tag}.json"
    json.dump(result, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n저장: {fp}")


if __name__ == "__main__":
    main()
