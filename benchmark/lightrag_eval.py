"""
LightRAG 검색 평가 (E6) — 골드셋으로 모드별 recall@k 측정.
- LightRAG 질의(only_need_context) → 반환 청크 내용을 원본 청크 텍스트와 매칭 → uid 역추적.
- 유형별(crossref/multihop 등) 분해. 하이브리드+리랭커(0.860)와 비교용.

사용 (전체 색인 완료 + Mistral 서빙 중):
  python benchmark/lightrag_eval.py --modes naive local global hybrid mix
"""
import sys
import json
import re
import argparse
import asyncio
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "pipeline"))
sys.path.insert(0, str(HERE / "eval"))
from chunkers import build_chunks      # noqa: E402
import retrieval_metrics as RM         # noqa: E402
import lightrag_index as LI            # noqa: E402
from common import LIGHTRAG_MODES, load_jsonl  # noqa: E402

CORPUS = json.load(open(HERE / "corpus_ids.json", encoding="utf-8"))


def text2uid_map():
    """청크 텍스트 앞부분(브레드크럼) → uid. LightRAG 반환 청크 역추적용."""
    m = {}
    for c in build_chunks("article", CORPUS, byeolpyo="md"):
        m[_key(c["text"])] = c["source_uids"][0]
    return m


def _key(text):
    return re.sub(r"\s+", " ", text[:70]).strip()


def parse_chunk_uids(context, t2u):
    """컨텍스트에서 반환 청크 content를 추출해 uid 순서대로 매핑(중복 제거)."""
    uids = []
    seen = set()
    for mt in re.finditer(r'"content":\s*"((?:[^"\\]|\\.)*)"', context):
        try:
            content = json.loads('"' + mt.group(1) + '"')
        except json.JSONDecodeError:
            continue
        uid = t2u.get(_key(content))
        if uid and uid not in seen:
            seen.add(uid)
            uids.append(uid)
    return uids


async def eval_mode(rag, mode, goldset, t2u, top_k=10):
    from lightrag import QueryParam
    per_type = defaultdict(list)
    per_q = []
    for q in goldset:
        try:
            ctx = await rag.aquery(q["question"],
                                   param=QueryParam(mode=mode, only_need_context=True,
                                                    top_k=top_k, chunk_top_k=top_k))
        except Exception:
            ctx = ""
        ranked_uids = parse_chunk_uids(str(ctx), t2u)
        ranked = [{"source_uids": [u]} for u in ranked_uids]   # 메트릭 형식
        m = RM.evaluate(ranked, q["gold_ids"])
        per_q.append(m); per_type[q["type"]].append(m)
    return RM.aggregate(per_q), {t: RM.aggregate(v) for t, v in per_type.items()}


async def main_async(args):
    rag = await LI.make_rag()
    t2u = text2uid_map()
    goldset = load_jsonl(HERE / "goldset" / "questions.jsonl")
    print(f"골드셋 {len(goldset)}문 | 청크맵 {len(t2u)}")
    for mode in args.modes:
        overall, by_type = await eval_mode(rag, mode, goldset, t2u, args.top_k)
        print(f"\n=== LightRAG mode={mode} ===")
        print(f"  전체  recall@1={overall['recall@1']:.3f} @5={overall['recall@5']:.3f} "
              f"@10={overall['recall@10']:.3f} | mrr={overall['mrr']:.3f} | ndcg@10={overall['ndcg@10']:.3f}")
        for t, mm in by_type.items():
            print(f"  {t:9s} recall@5={mm['recall@5']:.3f} | mrr={mm['mrr']:.3f}")
    await rag.finalize_storages()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=LIGHTRAG_MODES)
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
