"""
반자동 골드셋 생성
- 코퍼스 조문/별표에서 로컬 LLM(vLLM, OpenAI 호환)으로 Q&A 생성 → 근거 id 고정 → LLM 검증
- 질문 유형 4종 분산: factoid(정의/요건) / crossref(교차참조) / byeolpyo(별표조회) / multihop(위임·법↔시행령)
- factoid는 격식체+구어체 쌍(register, 공통 pair_id)으로 생성 → HyPE 어휘격차 효과 짝지어 측정
산출: questions.jsonl  {id, question, answer, gold_ids, type, register, pair_id, 법령명}

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
def chat(base_url, model, system, user, temperature=0.0, max_retries=3):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},  # vLLM 가이드 JSON — 파싱 안정화
    }
    def _post(pl):
        req = urllib.request.Request(url, data=json.dumps(pl).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer EMPTY"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]

    for i in range(max_retries):
        try:
            return _post(payload)
        except urllib.error.HTTPError as e:
            # response_format 미지원(400) 시 해당 키 제거 후 폴백
            if e.code == 400 and "response_format" in payload:
                payload.pop("response_format", None)
                continue
            if i < max_retries - 1:
                time.sleep(2)
            else:
                print(f"  [LLM HTTP {e.code}] {e}", file=sys.stderr)
                return None
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

# 격식체↔구어체 쌍 생성: 같은 의미를 (1)법률 격식체와 (2)일상 구어체로. 정답·근거는 동일.
# HyPE/임베딩의 '격식 조문 ↔ 구어 질문' 어휘격차 해소 효과를 짝지어(paired) 측정하기 위함.
GEN_PAIR_SYS = (
    "당신은 한국 금융 법령 전문가다. 주어진 조문만을 근거로, 같은 사실을 묻는 질문 2개를 만든다: "
    "(1) formal: 법률 격식체 질문, (2) colloquial: 같은 의미를 일반인이 일상적으로 묻는 구어체 질문"
    "(예: '~하면 어떻게 되나요?', '~해도 되나요?'). 정답은 둘에 공통. "
    "조문 번호는 노출하지 말 것. JSON으로만: "
    "{\"formal\": \"...\", \"colloquial\": \"...\", \"answer\": \"...\"}.")

TYPE_HINT = {
    "factoid": "정의·요건·기준 등 사실 관계를 묻는 질문.",
    "crossref": f"이 조문이 인용하는 다른 법령/제도와의 관계를 묻는 질문.",
    "byeolpyo": "별표의 구체적 수치·기준·항목 값을 묻는 질문.",
    "multihop": "이 조문이 대통령령 등 하위법령에 위임한 사항을 묻는 질문.",
}

JUDGE_SYS = (
    "골드셋 품질 심사관이다. 다음 두 가지를 판정한다: "
    "(1) grounded: '정답'이 '근거 텍스트'에 명시적으로 들어 있는가. "
    "(2) needs_context: 이 '질문'이 근거 텍스트 없이 일반 상식만으로는 답하기 어렵고, "
    "해당 법령 조문을 찾아봐야만 정확히 답할 수 있는가(=검색 평가에 적합한가). "
    "둘 다 참이어야 좋은 질문이다. JSON으로만: "
    "{\"grounded\": true/false, \"needs_context\": true/false, \"reason\": \"...\"}.")


def gen_qa(base_url, model, qtype, context, label):
    # temp=0: 골드셋을 완전 재현 가능하게(벤치마크 안정성). 질문 다양성은 수천 개
    # 서로 다른 조문에서 확보되므로 샘플링 온도에 의존하지 않음.
    user = (f"[질문 유형] {TYPE_HINT[qtype]}\n\n[근거 {label}]\n{context[:2500]}\n\n"
            "위 근거만으로 답할 수 있는 질문과 정답을 JSON으로 생성하라.")
    return parse_json(chat(base_url, model, GEN_SYS, user, temperature=0.0))


def gen_pair(base_url, model, context):
    """격식체+구어체 질문 쌍 생성(공통 정답). 1회 호출로 matched pair."""
    user = f"[근거 조문]\n{context[:2500]}\n\n격식체·구어체 질문 2개와 공통 정답을 JSON으로 생성하라."
    return parse_json(chat(base_url, model, GEN_PAIR_SYS, user, temperature=0.0))


def judge_qa(base_url, model, question, answer, context):
    user = f"[근거 텍스트]\n{context[:2500]}\n\n[질문] {question}\n[정답] {answer}"
    j = parse_json(chat(base_url, model, JUDGE_SYS, user, temperature=0.0))
    # grounded(정답이 근거에 존재) AND needs_context(일반상식으론 못 푸는 질문) 둘 다 참이어야 채택
    return bool(j and j.get("grounded") and j.get("needs_context"))


# ---------- 단위 풀 구성 ----------
def build_pools():
    """factoid/crossref/byeolpyo 풀 + multihop은 (본법조, 시행령조) 페어"""
    arts_all, byps_all = [], []
    families = {}  # 본법명 -> {'본법':[arts], '시행령':[arts]}
    for c in CORPUS:
        _, arts, byps = load_law(c["mst"])
        arts = [a for a in arts if not a.is_buchik and len(a.본문) >= 60]
        arts_all.extend(arts)
        for b in byps:
            if b.구분 == "별표" and (b.md_path or len(b.본문_평문) > 100):
                byps_all.append(b)
        fam = families.setdefault(c["본법"], {"본법": [], "시행령": []})
        if c["역할"] in ("본법", "시행령"):
            fam[c["역할"]].extend(arts)

    # multihop 페어: 본법 위임조('대통령령') ↔ 그 조를 명시 인용하는 시행령 조('법 제N조')
    # 엄격 매칭만 사용(느슨한 '제N조' 포함은 시행령 자기참조 등 오탐이 많아 제외)
    pairs = []
    for fam in families.values():
        siv = fam["시행령"]
        for a in fam["본법"]:
            if "대통령령" not in a.본문:
                continue
            n = a.조문번호
            # 가지번호까지 반영해 정확 매칭(제5조 ≠ 제5조의2). 가지 없으면 '의N'·숫자 연속을 배제.
            if a.가지번호:
                pat = rf"법\s*제{n}조의{a.가지번호}(?!\d)"
            else:
                pat = rf"법\s*제{n}조(?!의|\d)"
            cited = [s for s in siv if re.search(pat, s.본문)]
            if cited:
                pairs.append((a, cited[0]))

    return {
        "factoid": list(arts_all),
        "crossref": [a for a in arts_all if a.refs],
        "byeolpyo": byps_all,
        "multihop": pairs,  # [(본법조, 시행령조), ...]
    }


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

    results = []
    counter = {"n": 0}
    stats = {"gen_fail": 0, "judge_drop": 0}

    def emit(question, answer, gold, qtype, lawname, register="formal", pair_id=None):
        counter["n"] += 1
        results.append({"id": f"q{counter['n']:04d}", "question": question.strip(),
                        "answer": answer.strip(), "gold_ids": gold, "type": qtype,
                        "register": register, "pair_id": pair_id, "법령명": lawname})

    for qtype, pool in pools.items():
        RNG.shuffle(pool)
        picked = 0
        # factoid는 격식체+구어체 쌍 생성 → per_type을 절반(쌍 수)으로 잡아 질문 총량 균형
        target = max(1, args.per_type // 2) if qtype == "factoid" else args.per_type
        for unit in pool:
            if picked >= target:
                break
            # ---- factoid: 격식↔구어 쌍 ----
            if qtype == "factoid":
                ctx = article_context(unit)
                pair = gen_pair(args.base_url, args.model, ctx)
                if not (pair and pair.get("formal") and pair.get("colloquial") and pair.get("answer")):
                    stats["gen_fail"] += 1
                    continue
                if not args.no_judge and not judge_qa(args.base_url, args.model,
                                                      pair["formal"], pair["answer"], ctx):
                    stats["judge_drop"] += 1
                    continue
                pid = f"p{unit.uid}"
                emit(pair["formal"], pair["answer"], [unit.uid], "factoid", unit.법령명, "formal", pid)
                emit(pair["colloquial"], pair["answer"], [unit.uid], "factoid", unit.법령명, "colloquial", pid)
                picked += 1
                if counter["n"] % 10 == 0:
                    print(f"  생성 {counter['n']} (factoid 쌍 {picked}/{target})")
                time.sleep(0.05)
                continue
            # ---- 그 외 유형 ----
            if qtype == "byeolpyo":
                ctx = byeolpyo_context(unit); gold = [unit.uid]; lawname = unit.법령명; label = "별표"
            elif qtype == "multihop":
                base, impl = unit
                ctx = (f"[근거1·본법]\n{article_context(base)}\n\n"
                       f"[근거2·시행령]\n{article_context(impl)}")
                gold = [base.uid, impl.uid]; lawname = base.법령명; label = "본법+시행령"
            else:  # crossref
                ctx = article_context(unit); gold = [unit.uid]; lawname = unit.법령명; label = "조문"
            qa = gen_qa(args.base_url, args.model, qtype, ctx, label)
            if not qa or not qa.get("question") or not qa.get("answer"):
                stats["gen_fail"] += 1
                continue
            if not args.no_judge and not judge_qa(args.base_url, args.model,
                                                  qa["question"], qa["answer"], ctx):
                stats["judge_drop"] += 1
                continue
            emit(qa["question"], qa["answer"], gold, qtype, lawname)
            picked += 1
            if counter["n"] % 10 == 0:
                print(f"  생성 {counter['n']} (유형 {qtype} {picked}/{target})")
            time.sleep(0.05)

    with open(OUT, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"\n=== 골드셋 {len(results)}문 저장: {OUT} ===")
    print("유형별:", dict(Counter(r["type"] for r in results)))
    print("register별:", dict(Counter(r["register"] for r in results)))
    print("드롭:", stats)


if __name__ == "__main__":
    main()
