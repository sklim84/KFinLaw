"""
반자동 골드셋 생성
- 코퍼스 조문/별표에서 로컬 LLM(vLLM, OpenAI 호환)으로 Q&A 생성 → 근거 id 고정 → LLM 검증
- 질문 유형 4종 분산: factoid(정의/요건) / crossref(교차참조) / byeolpyo(별표조회) / multihop(위임·법↔시행령)
산출: benchmark/goldset/questions.jsonl  {id, question, answer, gold_ids, type, 법령명}

사용:
  # 먼저 vLLM 기동 (예): vllm serve Qwen/Qwen2.5-72B-Instruct --port 8000
  python benchmark/goldset/build_goldset.py --base-url http://localhost:8000/v1 --model Qwen/Qwen2.5-72B-Instruct
  python benchmark/goldset/build_goldset.py --smoke   # 유형별 2문만
"""
import json, re, argparse, urllib.request, time, sys, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lawdoc import load_law  # noqa: E402

HERE = Path(__file__).parent
CORPUS = json.load(open(HERE.parent / "corpus_ids.json", encoding="utf-8"))
OUT = HERE / "questions.jsonl"
RNG = random.Random(42)  # 재현성


# ---------- LLM 클라이언트 (OpenAI 호환, 의존성 없음) ----------
def chat(base_url, model, system, user, temperature=0.3, max_retries=3):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": 1024,
    }
    data = json.dumps(payload).encode()
    for i in range(max_retries):
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": "Bearer EMPTY"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                out = json.loads(resp.read())
            return out["choices"][0]["message"]["content"]
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(2)
            else:
                print(f"  [LLM ERROR] {e}", file=sys.stderr)
                return None


def parse_json(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ---------- 프롬프트 ----------
GEN_SYS = ("당신은 한국 금융 법령 전문가다. 주어진 법령 조문(또는 별표)만을 근거로, "
           "그 조문을 읽어야만 답할 수 있는 질문 1개와 간결한 정답을 만든다. "
           "반드시 JSON으로만 출력: {\"question\": \"...\", \"answer\": \"...\"}. "
           "질문에 조문 번호를 노출하지 말 것(검색 능력 평가용).")

TYPE_HINT = {
    "factoid": "정의·요건·기준 등 사실 관계를 묻는 질문.",
    "crossref": f"이 조문이 인용하는 다른 법령/제도와의 관계를 묻는 질문.",
    "byeolpyo": "별표의 구체적 수치·기준·항목 값을 묻는 질문.",
    "multihop": "이 조문이 대통령령 등 하위법령에 위임한 사항을 묻는 질문.",
}

JUDGE_SYS = ("주어진 '근거 텍스트'만으로 '질문'에 대한 '정답'이 도출 가능한지 판정한다. "
             "JSON으로만: {\"valid\": true/false, \"reason\": \"...\"}.")


def gen_qa(base_url, model, qtype, context, label):
    user = (f"[질문 유형] {TYPE_HINT[qtype]}\n\n[근거 {label}]\n{context[:2500]}\n\n"
            "위 근거만으로 답할 수 있는 질문과 정답을 JSON으로 생성하라.")
    return parse_json(chat(base_url, model, GEN_SYS, user))


def judge_qa(base_url, model, question, answer, context):
    user = f"[근거 텍스트]\n{context[:2500]}\n\n[질문] {question}\n[정답] {answer}"
    j = parse_json(chat(base_url, model, JUDGE_SYS, user, temperature=0.0))
    return bool(j and j.get("valid"))


# ---------- 단위 풀 구성 ----------
def build_pools():
    arts_all, byps_all = [], []
    for c in CORPUS:
        _, arts, byps = load_law(c["mst"])
        for a in arts:
            if a.is_buchik or len(a.본문) < 60:
                continue
            arts_all.append(a)
        for b in byps:
            if b.구분 == "별표" and (b.md_path or len(b.본문_평문) > 100):
                byps_all.append(b)
    pools = {
        "factoid": [a for a in arts_all],
        "crossref": [a for a in arts_all if a.refs],
        "multihop": [a for a in arts_all if ("대통령령" in a.본문 or "총리령" in a.본문)],
        "byeolpyo": byps_all,
    }
    return pools


def article_context(a):
    head = f"{a.법령명} 제{a.조문번호}조" + (f"의{a.가지번호}" if a.가지번호 else "")
    return f"{head}({a.제목})\n{a.본문}"


def byeolpyo_context(b):
    body = ""
    if b.md_path:
        body = Path(b.md_path).read_text(encoding="utf-8")[:2500]
    else:
        body = b.본문_평문[:2500]
    return f"{b.법령명} [별표{b.번호}] {b.제목}\n{body}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", default="Qwen/Qwen2.5-72B-Instruct")
    ap.add_argument("--per-type", type=int, default=60)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        args.per_type = 2

    pools = build_pools()
    print("단위 풀:", {k: len(v) for k, v in pools.items()})

    results, qid = [], 0
    stats = {"gen_fail": 0, "judge_drop": 0}
    for qtype, pool in pools.items():
        RNG.shuffle(pool)
        picked = 0
        for unit in pool:
            if picked >= args.per_type:
                break
            if qtype == "byeolpyo":
                ctx = byeolpyo_context(unit); gold = [unit.uid]; lawname = unit.법령명; label = "별표"
            else:
                ctx = article_context(unit); gold = [unit.uid]; lawname = unit.법령명; label = "조문"
            qa = gen_qa(args.base_url, args.model, qtype, ctx, label)
            if not qa or not qa.get("question") or not qa.get("answer"):
                stats["gen_fail"] += 1
                continue
            if not args.no_judge and not judge_qa(args.base_url, args.model,
                                                  qa["question"], qa["answer"], ctx):
                stats["judge_drop"] += 1
                continue
            qid += 1
            results.append({"id": f"q{qid:04d}", "question": qa["question"].strip(),
                            "answer": qa["answer"].strip(), "gold_ids": gold,
                            "type": qtype, "법령명": lawname})
            picked += 1
            if qid % 10 == 0:
                print(f"  생성 {qid} (유형 {qtype} {picked}/{args.per_type})")
            time.sleep(0.05)

    with open(OUT, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"\n=== 골드셋 {len(results)}문 저장: {OUT} ===")
    print("유형별:", dict(Counter(r["type"] for r in results)))
    print("드롭:", stats)


if __name__ == "__main__":
    main()
