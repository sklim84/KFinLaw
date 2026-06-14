"""
레이어2 답변 생성 평가 러너 (§8)
질문별: ① 검색(레이어1 최적 config 고정) → ② 답변 생성(답변모델) → ③ 채점(judge + 자동 인용검증).
검색 config를 고정해 '답변모델' 효과만 격리한다. judge는 답변모델과 다른 계열(자기우대 회피).

비교 축(--retrieval):
  good = 하이브리드+리랭커 top-k (레이어1 최적)   | bad = 단일 BM25 top-1 | none = closed-book(컨텍스트 없음)
  → good vs bad = '검색품질→답변품질' 전이, none = RAG 실효·환각 누출 대조(§8.3).

사용 (답변모델·judge를 다른 endpoint/계열로 서빙):
  python benchmark/answer_runner.py \
    --base-url http://localhost:8000/v1 --answer-model LGAI-EXAONE/EXAONE-4.0-32B \
    --judge-base-url http://localhost:8001/v1 --judge-model openai/gpt-oss-120b
  python benchmark/answer_runner.py --answer-model ... --retrieval none   # closed-book 대조
  python benchmark/answer_runner.py --answer-model ... --limit 20         # 스모크
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

from chunkers import build_chunks  # noqa: E402
from retrievers import build_retriever, Reranker  # noqa: E402
import answer_metrics as AM  # noqa: E402
from common import CONFIG, DEFAULT_ENDPOINT, load_json, load_jsonl, llm_chat, parse_json  # noqa: E402

CORPUS = load_json(HERE / "corpus_ids.json")
AE = CONFIG["answer_eval"]


# ---------- 답변 생성 프롬프트 ----------
RAG_SYS = (
    "당신은 한국 금융 법령 상담 전문가다. 아래 번호가 매겨진 [근거] 조문만을 바탕으로 질문에 "
    "정확하고 간결하게 답하라. 근거에 없는 내용은 지어내지 말고, 근거가 부족하면 '근거 부족'이라고 답하라. "
    "답에 실제로 사용한 근거 번호를 used_context에 정수 배열로 표기하라. "
    "JSON으로만 출력: {\"answer\": \"...\", \"used_context\": [정수, ...]}.")

CLOSED_SYS = (
    "당신은 한국 금융 법령 상담 전문가다. 제공되는 근거 없이 당신의 지식만으로 질문에 정확하고 간결하게 답하라. "
    "확실하지 않으면 모른다고 답하라. JSON으로만 출력: {\"answer\": \"...\"}.")


def build_context_retriever(mode, embedder_name):
    """검색 모드 → (retriever, n_context). none이면 (None, 0)."""
    if mode == "none":
        return None, 0
    byeolpyo = AE["retrieval"]["byeolpyo"]
    if mode == "bad":
        chunks = build_chunks("article", CORPUS, byeolpyo=byeolpyo)
        return build_retriever("bm25", chunks, top_k=1), 1
    # good: 레이어1 최적(조청킹 + 하이브리드 + 리랭커)
    r = AE["retrieval"]
    chunks = build_chunks(r["chunker"], CORPUS, byeolpyo=byeolpyo)
    from embedders import Embedder
    embedder = Embedder(embedder_name or r["embedder"])
    k = AE["context_top_k"]
    retr = build_retriever(r["retriever"], chunks, embedder=embedder, top_k=k)
    if r["rerank"]:
        retr = Reranker(retr, top_k=k)
    return retr, k


def uid_text_map():
    """uid → 청크 텍스트(브레드크럼 포함). 레퍼런스 근거 조문 제공·인용 라벨용."""
    m = {}
    for c in build_chunks("article", CORPUS, byeolpyo=AE["retrieval"]["byeolpyo"]):
        for u in c["source_uids"]:
            m.setdefault(u, c["text"])
    return m


def format_context(chunks):
    """회수 청크 → 번호 매긴 근거 블록 + 번호→uid 매핑.
    청크당 ctx_chars_per_chunk로 절단(긴 조문이 모델 창을 초과해 gold가 잘리는 것 방지)."""
    cap = AE["ctx_chars_per_chunk"]
    lines, idx2uids = [], {}
    for i, c in enumerate(chunks, 1):
        idx2uids[i] = list(c["source_uids"])
        lines.append(f"[{i}] {c['text'][:cap]}")
    return "\n\n".join(lines), idx2uids


def generate_answer(base_url, model, question, context_block, max_tokens, reasoning_effort):
    """답변모델 1회 호출 → (answer_text, used_context_indices). context_block=None이면 closed-book."""
    if context_block is None:
        out = parse_json(llm_chat(base_url, model, CLOSED_SYS, f"[질문] {question}",
                                  temperature=0.0, max_tokens=max_tokens,
                                  reasoning_effort=reasoning_effort))
        return (out or {}).get("answer", ""), []
    user = f"[근거]\n{context_block}\n\n[질문] {question}"
    out = parse_json(llm_chat(base_url, model, RAG_SYS, user, temperature=0.0,
                              max_tokens=max_tokens, reasoning_effort=reasoning_effort)) or {}
    used = [n for n in (_as_int(x) for x in (out.get("used_context") or [])) if n is not None]
    return out.get("answer", ""), used


def _as_int(x):
    """근거 번호 정규화: 1 / "2" / 3.0 → 정수, 그 외("x") → None."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else None


def run(args):
    retr, n_ctx = build_context_retriever(args.retrieval, args.embedder)
    u2t = uid_text_map()
    goldset = load_jsonl(args.goldset)
    if args.limit:
        goldset = goldset[:args.limit]
    judge_url = args.judge_base_url or args.base_url
    print(f"답변모델={args.answer_model} | judge={args.judge_model} | 검색={args.retrieval}"
          f"(n_ctx={n_ctx}) | 골드셋 {len(goldset)}문")
    if args.judge_model == args.answer_model:
        print("  [경고] judge=답변모델 → self-enhancement(자기우대) 편향. 다른 계열 분리 권장(§8.4).")
    if args.judge_base_url is None and args.judge_model != args.answer_model:
        print(f"  [경고] judge endpoint 미지정 → 답변모델과 같은 {judge_url} 사용. "
              "vLLM은 단일 모델만 서빙하므로 judge 호출이 실패할 수 있음. --judge-base-url로 분리 권장.")

    per_q, per_type, per_reg = [], defaultdict(list), defaultdict(list)
    t0 = time.time()
    for i, q in enumerate(goldset, 1):
        # ① 검색 → 컨텍스트
        if retr is None:
            ctx_block, idx2uids = None, {}
        else:
            chunks = [c for c, _ in retr.search(q["question"], top_k=n_ctx)]
            ctx_block, idx2uids = format_context(chunks)
        # ② 답변 생성
        answer, used = generate_answer(args.base_url, args.answer_model, q["question"],
                                       ctx_block, AE["max_answer_tokens"], args.reasoning_effort)
        # ③-a 인용 정확도(자동) — 컨텍스트 있을 때만
        m = {}
        if retr is not None:
            cited_uids = set()
            for n in used:
                cited_uids.update(idx2uids.get(n, []))
            m.update(AM.citation_metrics(cited_uids, q["gold_ids"]))
        # ③-b judge 루브릭(레퍼런스 기반). gold 본문도 청크당 동일 상한으로 절단(창 초과 방지)
        cap = AE["ctx_chars_per_chunk"]
        gold_ctx = "\n\n".join(u2t.get(g, f"(uid {g} 본문 없음)")[:cap] for g in q["gold_ids"])
        retrieved_ctx = ctx_block
        jr = AM.judge_answer(judge_url, args.judge_model, q["question"], q["answer"],
                             gold_ctx, retrieved_ctx, answer, args.judge_reasoning_effort)
        if jr:
            m.update(jr)
        per_q.append(m)
        per_type[q["type"]].append(m)
        per_reg[q.get("register", "formal")].append(m)
        if i % 10 == 0:
            print(f"  {i}/{len(goldset)} | {(time.time()-t0):.0f}s")

    result = {
        "config": {"answer_model": args.answer_model, "judge_model": args.judge_model,
                   "retrieval": args.retrieval, "n_context": n_ctx},
        "n_questions": len(goldset),
        "overall": AM.aggregate(per_q),
        "by_type": {t: AM.aggregate(v) for t, v in per_type.items()},
        "by_register": {r: AM.aggregate(v) for r, v in per_reg.items()},
        "timing_s": round(time.time() - t0, 1),
    }
    return result


def print_report(r):
    o = r["overall"]
    print(f"\n{'='*70}")
    c = r["config"]
    print(f"답변모델={c['answer_model']} | 검색={c['retrieval']}(n={c['n_context']}) | "
          f"judge={c['judge_model']} | {r['n_questions']}문 | {r['timing_s']}s")
    print("-"*70)

    def line(tag, m):
        cells = []
        for k in ("correctness", "faithfulness", "relevancy", "completeness",
                  "context_utilization", "cite_f1"):
            if k in m:
                cells.append(f"{k[:4]}={m[k]:.2f}")
        print(f"  {tag:11s} " + " ".join(cells))

    line("전체", o)
    for t, m in r["by_type"].items():
        line(t, m)
    reg = r.get("by_register", {})
    if len(reg) > 1:
        for rr, m in reg.items():
            line(f"[{rr}]", m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_ENDPOINT, help="답변모델 endpoint")
    ap.add_argument("--answer-model", default=CONFIG["models"]["answer_models"][0])
    ap.add_argument("--judge-base-url", default=None, help="judge endpoint(미지정 시 답변모델과 동일 추정)")
    ap.add_argument("--judge-model", default=CONFIG["models"]["judge"])
    ap.add_argument("--embedder", default=None, help="검색 임베더(미지정 시 config answer_eval)")
    ap.add_argument("--retrieval", default="good", choices=["good", "bad", "none"],
                    help="good=하이브리드+리랭커 / bad=BM25 top-1 / none=closed-book")
    ap.add_argument("--reasoning-effort", default=None, help="답변모델 추론수준(예: none)")
    ap.add_argument("--judge-reasoning-effort", default=None)
    ap.add_argument("--limit", type=int, default=0, help="스모크: 앞 N문만")
    ap.add_argument("--goldset", default=str(HERE / "goldset" / "questions.jsonl"))
    ap.add_argument("--out", default=str(HERE / "reports"))
    args = ap.parse_args()

    result = run(args)
    print_report(result)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    safe = args.answer_model.replace("/", "_")
    fp = Path(args.out) / f"answer_{safe}_{args.retrieval}.json"
    json.dump(result, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n저장: {fp}")


if __name__ == "__main__":
    main()
