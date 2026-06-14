"""
HyDE (Hypothetical Document Embeddings, Gao et al. 2023) 질의측 캐시 생성 (E7)
- 각 골드셋 질문에 대해 LLM이 '가설 답변(조문 문체)'을 1개 생성 → 캐시.
- 검색 시 원 질문 대신 이 가설 답변을 임베딩(retrievers.HyDERetriever)해 dense 검색.
  질의↔조문 어휘격차를 '질의측'에서 보정(HyPE=색인측의 대칭 기법).
- temp=0·reasoning_effort=none로 재현 가능. vLLM 동시호출(ThreadPoolExecutor).

사용 (Mistral 서빙 중):
  python -m benchmark.hyde_gen --reasoning-effort none --workers 16
산출: benchmark/hyde_cache.json  {question: hypothetical_doc}
"""
import json
import argparse
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from benchmark.common import CONFIG, DEFAULT_ENDPOINT, load_jsonl, llm_chat

HERE = Path(__file__).parent
GOLD = HERE / "goldset" / "questions.jsonl"
OUT = HERE / "hyde_cache.json"

HYDE_SYS = (
    "당신은 한국 금융 법령 전문가다. 사용자의 질문에 답하는 법령 조문을 실제 법령 문체로 "
    "1개 문단(2~4문장)으로 작성하라. 정확하지 않아도 좋으니 해당 조문에 담길 법한 내용을 "
    "구체적으로 기술한다. 질문을 반복하지 말고 답변 본문만 출력.")


def gen_doc(base_url, model, question, reasoning_effort):
    """질문 → 가설 답변 조문(평문). json_mode=False(자유 텍스트)."""
    return (llm_chat(base_url, model, HYDE_SYS, f"[질문] {question}",
                     temperature=0.0, max_tokens=256, json_mode=False,
                     reasoning_effort=reasoning_effort) or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_ENDPOINT)
    ap.add_argument("--model", default=CONFIG["models"]["generator"])
    ap.add_argument("--reasoning-effort", default="none")
    ap.add_argument("--workers", type=int, default=CONFIG["hype"]["workers"])
    args = ap.parse_args()

    goldset = load_jsonl(GOLD)
    questions = sorted({q["question"] for q in goldset})
    cache = json.load(open(OUT, encoding="utf-8")) if OUT.exists() else {}
    todo = [q for q in questions if q not in cache]
    print(f"질문 {len(questions)} | 생성 대상 {len(todo)} | workers {args.workers}")

    t0 = time.time()
    done = {"n": 0}

    def work(q):
        doc = gen_doc(args.base_url, args.model, q, args.reasoning_effort)
        done["n"] += 1
        if done["n"] % 50 == 0:
            print(f"  {done['n']}/{len(todo)} | {time.time()-t0:.0f}s")
        return q, doc

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for q, doc in ex.map(work, todo):
            cache[q] = doc

    json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    empty = sum(1 for v in cache.values() if not v)
    print(f"\n=== HyDE 캐시 저장: {OUT} ({len(cache)}개, 빈 응답 {empty}) ===")


if __name__ == "__main__":
    main()
