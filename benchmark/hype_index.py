"""
HyPE (Hypothetical Prompt Embeddings) 색인 생성
- 색인 시점에 각 청크가 답할 수 있는 가설 질문 N개를 LLM으로 생성 → 캐시.
- 검색 시 질문↔질문 매칭(retrievers.HyPERetriever). 격식 조문↔구어 질문 어휘격차 해소가 목적.
- vLLM 서버 배칭을 위해 동시 호출(ThreadPoolExecutor). temp=0·reasoning_effort=none로 재현 가능.

사용 (Mistral 서빙 중):
  python -m benchmark.hype_index --model mistralai/Mistral-Small-4-119B-2603 \
    --reasoning-effort none --n 5 --workers 16
산출: benchmark/hype_cache.json  {chunk_id: ["질문1", ...]}
"""
import json
import argparse
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from benchmark.pipeline.chunkers import build_chunks
from benchmark.common import CONFIG, CTX_CHARS, DEFAULT_ENDPOINT, load_json, llm_chat, parse_json

HERE = Path(__file__).parent
CORPUS = load_json(HERE / "corpus_ids.json")
OUT = HERE / "hype_cache.json"

HYPE_SYS = (
    "당신은 한국 금융 법령 전문가다. 주어진 법령 텍스트를 읽고, 이 텍스트만으로 답할 수 있는 "
    "자연스러운 한국어 질문 {n}개를 생성한다. 격식체와 일상 구어체를 섞고, 서로 다른 측면을 묻는다. "
    "조문 번호는 노출하지 말 것. JSON으로만: {{\"questions\": [\"...\", ...]}}.")


def gen_questions(base_url, model, text, n, reasoning_effort):
    sys_p = HYPE_SYS.format(n=n)
    user = f"[법령 텍스트]\n{text[:CTX_CHARS]}\n\n이 텍스트로 답할 수 있는 질문 {n}개를 JSON으로 생성하라."
    out = llm_chat(base_url, model, sys_p, user, temperature=0.0, reasoning_effort=reasoning_effort)
    j = parse_json(out)
    if not j:
        return []
    qs = j.get("questions", [])
    return [q.strip() for q in qs if isinstance(q, str) and len(q.strip()) > 5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_ENDPOINT)
    ap.add_argument("--model", default=CONFIG["models"]["generator"])
    ap.add_argument("--reasoning-effort", default="none")
    ap.add_argument("--n", type=int, default=CONFIG["hype"]["n_questions"], help="청크당 가설 질문 수")
    ap.add_argument("--workers", type=int, default=CONFIG["hype"]["workers"], help="동시 호출 수(vLLM 배칭)")
    ap.add_argument("--byeolpyo", default="md")
    ap.add_argument("--chunker", default="article")
    args = ap.parse_args()

    chunks = build_chunks(args.chunker, CORPUS, byeolpyo=args.byeolpyo)
    print(f"대상 청크: {len(chunks)} | 청크당 질문 {args.n} | workers {args.workers}")

    cache = {}
    if OUT.exists():
        cache = json.load(open(OUT, encoding="utf-8"))
        print(f"기존 캐시 {len(cache)}개 — 미생성분만 채움")
    todo = [c for c in chunks if c["chunk_id"] not in cache]
    print(f"생성 대상: {len(todo)}")

    t0 = time.time()
    done = {"n": 0}

    def work(c):
        qs = gen_questions(args.base_url, args.model, c["text"], args.n, args.reasoning_effort)
        done["n"] += 1
        if done["n"] % 100 == 0:
            el = time.time() - t0
            print(f"  {done['n']}/{len(todo)} | {done['n']/el:.1f} chunk/s | {el:.0f}s")
        return c["chunk_id"], qs

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for cid, qs in ex.map(work, todo):
            cache[cid] = qs

    json.dump(cache, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    nq = sum(len(v) for v in cache.values())
    empty = sum(1 for v in cache.values() if not v)
    print(f"\n=== HyPE 캐시 저장: {OUT} ===")
    print(f"청크 {len(cache)} | 총 가설질문 {nq} | 평균 {nq/max(len(cache),1):.1f}/청크 | 빈 청크 {empty}")
    print(f"소요 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
