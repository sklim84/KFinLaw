"""
반자동 골드셋 생성
- 코퍼스 조문/별표에서 로컬 LLM(vLLM, OpenAI 호환)으로 Q&A 생성 → 근거 id 고정 → LLM 검증
- 질문 유형 4종 분산: factoid(정의/요건) / crossref(교차참조) / byeolpyo(별표조회) / multihop(위임·법↔시행령)
- factoid는 격식체+구어체 쌍(register, 공통 pair_id)으로 생성 → HyPE 어휘격차 효과 짝지어 측정
산출: questions.jsonl  {id, question, answer, gold_ids, type, register, pair_id, 법령명}

검증 2단계(오염 회피):
  1) 일관성 필터(기본 ON, 모델 불필요): 질문→검색기 round-trip으로 원본 조문 회수 여부
  2) LLM judge(선택): grounded + needs_context. **생성기와 다른 계열 모델 권장**(preference leakage)
  → 1차(검색) 골드셋은 --no-judge로 일관성 필터만 써도 충분(LLM-judge 오염 완전 회피)

사용:
  # 생성기와 judge를 다른 endpoint/계열로 분리
  python -m benchmark.goldset.build_goldset \
    --base-url http://localhost:8000/v1 --model LGAI-EXAONE/EXAONE-4.0-32B \
    --judge-base-url http://localhost:8001/v1 --judge-model upstage/Solar-Open-100B
  # 1차 검색용(일관성 필터만, judge 생략):
  python -m benchmark.goldset.build_goldset --base-url ... --model ... --no-judge
  python -m benchmark.goldset.build_goldset --smoke

Semantic Benchmark 모드(--lowoverlap): HyPE/HyDE 부정 결과의 '일반화 가능성' 검증용 대조셋.
  - 기본 모드 = Lexical Benchmark(questions.jsonl): 조문 용어가 그대로 들어가 어휘중첩이 큼.
  - --lowoverlap = Semantic Benchmark(questions_lowoverlap.jsonl): 일상어로 풀어 어휘중첩이 작음
    (lowoverlap = low lexical overlap, 생성 방식을 가리키는 코드 식별자).
  기본 골드셋은 (a) 조문에서 생성돼 핵심 용어가 새고 (b) BM25 일관성 필터로 어휘중첩 큰 질문만
  채택돼 lexical 검색에 유리하게 편향됨. --lowoverlap은 검색기 무관하게:
    ① 법령명·조문번호·고유 전문용어를 빼고 일상어로 풀어 묻게 생성(쌍 없이 유형당 단일 질문)
    ② 결정론적 어휘중첩 필터 — 질문이 정답 조문의 '희소 4-gram'을 재사용하면 폐기(judge·일관성 미사용)
  산출: questions_lowoverlap.jsonl
  python -m benchmark.goldset.build_goldset --lowoverlap --reasoning-effort none
"""
import json
import re
import argparse
import time
import random
from collections import Counter
from pathlib import Path

from benchmark.lawdoc import load_law
from benchmark.common import (CTX_CHARS, DEFAULT_ENDPOINT, CONFIG, load_json,
                              llm_chat as chat, parse_json)

HERE = Path(__file__).parent
CORPUS = load_json(HERE.parent / "corpus_ids.json")
OUT = HERE / "questions.jsonl"
RNG = random.Random(42)  # 재현성


# ---------- 일관성(round-trip) 필터 (모델 불필요, 오염 없음) ----------
# Promptagator/InPars 기법: 생성 질문을 검색기에 넣어 원본 조문이 회수되는 질문만 채택.
# 표면중첩·주제이탈·미접지(ungrounded) 질문을 LLM 없이 제거 → LLM-judge 의존(및 오염)을 줄임.
# 주의: BM25(어휘적)는 구어체 질문을 과소평가할 수 있어, factoid 쌍은 '격식체'로 검사하고
#       구어체는 같은 정답을 공유하므로 함께 채택(콜로퀴얼 페널티 회피).
def build_consistency(retriever_kind="bm25", k=10):
    from benchmark.pipeline.chunkers import build_chunks
    from benchmark.pipeline.retrievers import build_retriever
    chunks = build_chunks("article", CORPUS, byeolpyo="md")  # 조문 + 별표
    retr = build_retriever(retriever_kind, chunks, top_k=max(k, 20))

    def passes(question, gold_ids):
        found = set()
        for c, _ in retr.search(question, top_k=k):
            found |= set(c["source_uids"])
        return bool(set(gold_ids) & found)  # 멀티홉은 하나라도 회수되면 통과(관대)
    return passes


# ---------- 어휘중첩(용어 누출) 필터 — --lowoverlap 전용, 검색기 무관·결정론적 ----------
def kgrams(text, n=4):
    s = re.sub(r"[^가-힣]", "", text)              # 한글만 남겨 josa·띄어쓰기 영향 제거
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def build_df(corpus):
    """코퍼스 청크별 4-gram 집합 → 문서빈도(DF). 희소 4-gram = 특정 조문에만 나오는 '앵커'."""
    from benchmark.pipeline.chunkers import build_chunks
    df = Counter()
    for c in build_chunks("article", corpus, byeolpyo="md"):
        for g in kgrams(c["text"]):
            df[g] += 1
    return df


def leaks_anchor(question, chunk_text, df, max_df=5):
    """질문이 정답 조문의 '희소(DF<=max_df) 4-gram'을 재사용하면 True(=용어 누출, 폐기)."""
    shared = kgrams(question) & kgrams(chunk_text)
    return any(df.get(g, 0) <= max_df for g in shared)


# ---------- LLM 클라이언트·JSON 파서는 common(llm_chat/parse_json)에서 공유 ----------


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
    "crossref": "이 조문이 인용하는 다른 법령/제도와의 관계를 묻는 질문.",
    "byeolpyo": "별표의 구체적 수치·기준·항목 값을 묻는 질문.",
    "multihop": "이 조문이 대통령령 등 하위법령에 위임한 사항을 묻는 질문.",
}

# --lowoverlap 전용: 고유 용어를 빼고 일상어로 풀어 묻게 하는 생성 프롬프트.
GEN_SYS_LO = (
    "당신은 한국 금융 법령 전문가다. 주어진 조문(또는 별표)만 근거로, 그 내용을 찾아봐야만 답할 수 있는 "
    "질문 1개와 간결한 정답을 만든다. 단 질문은 **일반인이 상황을 일상어로 설명하듯** 쓰고, "
    "**법령명·조문번호, 그리고 그 조문에만 나오는 고유 전문용어/정식 명칭을 절대 그대로 쓰지 말 것**. "
    "그런 용어는 일상적 표현으로 풀어 쓴다 (예: '예금보험기금채권상환특별기여금'→'예금보험 관련 부담금', "
    "'부가통신업자'→'결제 중계 사업자'). JSON으로만: {\"question\": \"...\", \"answer\": \"...\"}.")
TYPE_HINT_LO = {
    "factoid": "정의·요건·기준 등 사실 관계를 상황으로 풀어 묻는 질문.",
    "crossref": "이 조문이 다른 법령/제도와 어떻게 연결되는지를 상황으로 묻는 질문.",
    "byeolpyo": "별표의 구체적 수치·기준·항목 값을 상황으로 묻는 질문.",
    "multihop": "이 조문이 하위법령(대통령령 등)에 위임한 사항을 상황으로 묻는 질문.",
}

JUDGE_SYS = (
    "골드셋 품질 심사관이다. 다음 두 가지를 판정한다: "
    "(1) grounded: '정답'이 '근거 텍스트'에 명시적으로 들어 있는가. "
    "(2) needs_context: 이 '질문'이 근거 텍스트 없이 일반 상식만으로는 답하기 어렵고, "
    "해당 법령 조문을 찾아봐야만 정확히 답할 수 있는가(=검색 평가에 적합한가). "
    "둘 다 참이어야 좋은 질문이다. JSON으로만: "
    "{\"grounded\": true/false, \"needs_context\": true/false, \"reason\": \"...\"}.")


def gen_qa(base_url, model, qtype, context, label, reasoning_effort=None, lowoverlap=False):
    # temp=0: 골드셋을 완전 재현 가능하게(벤치마크 안정성). 질문 다양성은 수천 개
    # 서로 다른 조문에서 확보되므로 샘플링 온도에 의존하지 않음.
    sysmsg = GEN_SYS_LO if lowoverlap else GEN_SYS
    hint = (TYPE_HINT_LO if lowoverlap else TYPE_HINT)[qtype]
    tail = ("위 근거로 답할 수 있는, 고유 용어를 쓰지 않은 일상어 질문과 정답을 JSON으로 생성하라."
            if lowoverlap else "위 근거만으로 답할 수 있는 질문과 정답을 JSON으로 생성하라.")
    user = f"[질문 유형] {hint}\n\n[근거 {label}]\n{context[:CTX_CHARS]}\n\n{tail}"
    return parse_json(chat(base_url, model, sysmsg, user, temperature=0.0,
                           reasoning_effort=reasoning_effort))


def gen_pair(base_url, model, context, reasoning_effort=None):
    """격식체+구어체 질문 쌍 생성(공통 정답). 1회 호출로 matched pair."""
    user = f"[근거 조문]\n{context[:CTX_CHARS]}\n\n격식체·구어체 질문 2개와 공통 정답을 JSON으로 생성하라."
    return parse_json(chat(base_url, model, GEN_PAIR_SYS, user, temperature=0.0,
                           reasoning_effort=reasoning_effort))


def judge_qa(base_url, model, question, answer, context, reasoning_effort=None):
    user = f"[근거 텍스트]\n{context[:CTX_CHARS]}\n\n[질문] {question}\n[정답] {answer}"
    j = parse_json(chat(base_url, model, JUDGE_SYS, user, temperature=0.0,
                        reasoning_effort=reasoning_effort))
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
        body = Path(b.md_path).read_text(encoding="utf-8")[:CTX_CHARS]
    else:
        body = b.본문_평문[:CTX_CHARS]
    return f"{b.법령명} [별표{b.번호}] {b.제목}\n{body}"


def main():
    ap = argparse.ArgumentParser()
    # 생성기(generator)
    ap.add_argument("--base-url", default=DEFAULT_ENDPOINT)
    ap.add_argument("--model", default=CONFIG["models"]["generator"])
    # judge(검증기) — 생성기와 다른 계열 권장(preference leakage 회피). 미지정 시 생성기와 동일(경고).
    ap.add_argument("--judge-base-url", default=None)
    ap.add_argument("--judge-model", default=None)
    # reasoning_effort: Mistral Small 4 등 추론모델의 공식 per-request 파라미터. 생성엔 "none" 권장.
    ap.add_argument("--reasoning-effort", default=None, help="생성기 추론수준(예: none). Mistral 계열 필수")
    ap.add_argument("--judge-reasoning-effort", default=None, help="judge 추론수준(예: none)")
    ap.add_argument("--per-type", type=int, default=CONFIG["goldset"]["per_type"])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--no-judge", action="store_true", help="LLM judge 생략(일관성 필터만으로 검증)")
    # 일관성(round-trip) 필터 — 모델 불필요, 기본 ON
    ap.add_argument("--no-consistency", action="store_true")
    ap.add_argument("--ck", type=int, default=CONFIG["goldset"]["consistency_top_k"],
                    help="일관성 필터 top-k")
    # 저어휘중첩 split: 일상어 생성 + 4-gram DF 누출 필터(judge·일관성 미사용), 별도 파일로 저장
    ap.add_argument("--lowoverlap", action="store_true",
                    help="저어휘중첩 모드(어휘격차 큰 질의셋, questions_lowoverlap.jsonl)")
    ap.add_argument("--max-df", type=int, default=5, help="lowoverlap 희소 4-gram 판정 DF 상한")
    args = ap.parse_args()
    if args.smoke:
        args.per_type = 2

    out = HERE / ("questions_lowoverlap.jsonl" if args.lowoverlap else "questions.jsonl")
    judge_url = args.judge_base_url or args.base_url
    judge_model = args.judge_model or args.model
    if not args.lowoverlap and not args.no_judge and judge_model == args.model:
        print("  [경고] judge 모델이 생성기와 동일 → preference leakage 위험. "
              "--judge-model로 다른 계열 분리 권장(또는 --no-judge로 일관성 필터만 사용).")

    # lowoverlap은 검색기 무관 4-gram 필터만 사용(judge·일관성 비활성). 그 외는 일관성 필터(기본 ON).
    df = build_df(CORPUS) if args.lowoverlap else None
    passes = None if (args.no_consistency or args.lowoverlap) else build_consistency(k=args.ck)
    pools = build_pools()
    print("단위 풀:", {k: len(v) for k, v in pools.items()})
    if args.lowoverlap:
        print(f"생성기={args.model} | 모드=lowoverlap | 누출필터=4gram-DF<={args.max_df} "
              f"(DF 종류 {len(df)})")
    else:
        print(f"생성기={args.model} | judge={'OFF' if args.no_judge else judge_model} | "
              f"일관성필터={'OFF' if args.no_consistency else 'BM25@'+str(args.ck)}")

    results = []
    counter = {"n": 0}
    stats = {"gen_fail": 0, "judge_drop": 0, "consistency_drop": 0, "overlap_drop": 0}

    idpfx = "lo" if args.lowoverlap else "q"
    def emit(question, answer, gold, qtype, lawname, register="formal", pair_id=None):
        counter["n"] += 1
        results.append({"id": f"{idpfx}{counter['n']:04d}", "question": question.strip(),
                        "answer": answer.strip(), "gold_ids": gold, "type": qtype,
                        "register": register, "pair_id": pair_id, "법령명": lawname})

    pair_mode = not args.lowoverlap   # lowoverlap은 쌍 없이 유형당 단일 질문
    for qtype, pool in pools.items():
        # 재현성: 표준 모드는 공유 RNG(연속), lowoverlap은 유형별 독립 시드(기존 산출물과 동일)
        (random.Random(42).shuffle if args.lowoverlap else RNG.shuffle)(pool)
        picked = 0
        # factoid는 격식체+구어체 쌍 생성 → per_type을 절반(쌍 수)으로 잡아 질문 총량 균형
        target = max(1, args.per_type // 2) if (qtype == "factoid" and pair_mode) else args.per_type
        for unit in pool:
            if picked >= target:
                break
            # ---- factoid: 격식↔구어 쌍 (표준 모드만) ----
            if qtype == "factoid" and pair_mode:
                ctx = article_context(unit)
                pair = gen_pair(args.base_url, args.model, ctx, args.reasoning_effort)
                if not (pair and pair.get("formal") and pair.get("colloquial") and pair.get("answer")):
                    stats["gen_fail"] += 1
                    continue
                if not args.no_judge and not judge_qa(judge_url, judge_model,
                                                      pair["formal"], pair["answer"], ctx,
                                                      args.judge_reasoning_effort):
                    stats["judge_drop"] += 1
                    continue
                # 일관성: 격식체로 검사(구어체는 같은 정답 공유 → 함께 채택, 콜로퀴얼 페널티 회피)
                if passes and not passes(pair["formal"], [unit.uid]):
                    stats["consistency_drop"] += 1
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
            else:  # crossref / (lowoverlap의) factoid
                ctx = article_context(unit); gold = [unit.uid]; lawname = unit.법령명; label = "조문"
            qa = gen_qa(args.base_url, args.model, qtype, ctx, label, args.reasoning_effort,
                        lowoverlap=args.lowoverlap)
            if not qa or not qa.get("question") or not qa.get("answer"):
                stats["gen_fail"] += 1
                continue
            if args.lowoverlap:
                if leaks_anchor(qa["question"], ctx, df, args.max_df):  # 용어 누출 → 폐기
                    stats["overlap_drop"] += 1
                    continue
            else:
                if not args.no_judge and not judge_qa(judge_url, judge_model,
                                                      qa["question"], qa["answer"], ctx,
                                                      args.judge_reasoning_effort):
                    stats["judge_drop"] += 1
                    continue
                if passes and not passes(qa["question"], gold):
                    stats["consistency_drop"] += 1
                    continue
            emit(qa["question"], qa["answer"], gold, qtype, lawname,
                 register="lowoverlap" if args.lowoverlap else "formal")
            picked += 1
            if counter["n"] % 10 == 0:
                print(f"  생성 {counter['n']} (유형 {qtype} {picked}/{target})")
            time.sleep(0.05)

    with open(out, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n=== 골드셋 {len(results)}문 저장: {out} ===")
    print("유형별:", dict(Counter(r["type"] for r in results)))
    print("register별:", dict(Counter(r["register"] for r in results)))
    print("드롭:", stats)


if __name__ == "__main__":
    main()
