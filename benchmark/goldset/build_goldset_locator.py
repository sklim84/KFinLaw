"""
Locator Benchmark 생성 — known-item(조문 위치 지정) 질의. **결정론적, LLM 불요.**

사용자가 위치(법령명+조번호)를 이미 알고 그 조문을 찾는 질의. dense 검색의 '정확 식별자/숫자'
맹점(EntityQuestions·AmbER, 법률 CLaw·CLERC에서 보고)을 한국 금융법 도메인에서 측정한다.

유형(검색 gold가 조 단위 청킹에서 실제로 달라지는 것만):
  loc_single  "○○법 제5조 …"              gold = 그 조문 1개
  loc_range   "○○법 제5조부터 제8조까지 …"   gold = 범위 내 조문들(멀티-gold)
  loc_ambig   "제5조 …"(법령명 생략)         gold = 코퍼스 내 '제5조' 전부 → 숫자 매칭만으로 가능(AmbER식)
(조+항·조+항범위는 조 단위 색인에서 gold가 조와 동일해 제외 — 항 수준은 항 청킹 별도 서브실험)

산출: benchmark/goldset/questions_locator.jsonl (스키마는 기존 골드셋과 동일)
사용: python -m benchmark.goldset.build_goldset_locator   (LLM·GPU 불필요)
"""
import json
import argparse
import random
from collections import defaultdict
from pathlib import Path

from benchmark.lawdoc import load_law
from benchmark.common import load_json

HERE = Path(__file__).parent
CORPUS = load_json(HERE.parent / "corpus_ids.json")
OUT = HERE / "questions_locator.jsonl"
RNG = random.Random(42)


def load_articles():
    """법령별 조문 목록(부칙·초단문 제외) + 전체."""
    by_law, all_arts = {}, []
    for c in CORPUS:
        _, arts, _ = load_law(c["mst"])
        arts = [a for a in arts if not a.is_buchik and len(a.본문) >= 40]
        if arts:
            by_law.setdefault(arts[0].법령명, []).extend(arts)
            all_arts.extend(arts)
    return by_law, all_arts


def jono(a):
    return f"제{a.조문번호}조" + (f"의{a.가지번호}" if a.가지번호 else "")


def jonum(a):
    """조문번호 정수값(범위 계산용). 비정수면 None."""
    try:
        return int(a.조문번호)
    except (ValueError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=40)
    args = ap.parse_args()

    by_law, all_arts = load_articles()
    # 번호별 인덱스(법령명 생략 모호질의용): 가지 없는 '제N조'만
    by_num = defaultdict(list)
    for a in all_arts:
        if not a.가지번호 and jonum(a) is not None:
            by_num[jonum(a)].append(a)

    rows, n = [], 0

    def emit(q, gold, qtype, lawname, answer=""):
        nonlocal n
        n += 1
        rows.append({"id": f"loc{n:04d}", "question": q, "answer": answer,
                     "gold_ids": gold, "type": qtype, "register": "locator", "법령명": lawname})

    # ---- L1 단일 조 ----
    pool = all_arts[:]
    RNG.shuffle(pool)
    for a in pool[:args.per_type]:
        emit(f"{a.법령명} {jono(a)}에는 어떤 내용이 규정되어 있나요?",
             [a.uid], "loc_single", a.법령명, a.제목)

    # ---- L2 조 범위 (한 법령 내 연속 조문 번호 구간) ----
    laws = [(name, arts) for name, arts in by_law.items()
            if len({jonum(x) for x in arts if jonum(x) is not None}) >= 8]
    RNG.shuffle(laws)
    made = 0
    for name, arts in laws:
        if made >= args.per_type:
            break
        nums = sorted({jonum(x) for x in arts if jonum(x) is not None})
        # 구간 길이 3~5의 연속 '번호값'(정수 연속) 구간 후보를 찾는다
        starts = [i for i in range(len(nums) - 3) if nums[i + 3] - nums[i] <= 6]
        if not starts:
            continue
        i = RNG.choice(starts)
        span = RNG.randint(3, 5)
        j = min(i + span - 1, len(nums) - 1)
        s, e = nums[i], nums[j]
        gold = [x.uid for x in arts if jonum(x) is not None and s <= jonum(x) <= e]
        if not (2 <= len(gold) <= 8):
            continue
        emit(f"{name} 제{s}조부터 제{e}조까지에는 무엇이 규정되어 있나요?",
             gold, "loc_range", name, f"제{s}~{e}조")
        made += 1

    # ---- L3 법령명 생략/모호 (제N조, gold = 코퍼스 내 제N조 전부) ----
    cand = [num for num, lst in by_num.items() if len(lst) >= 3]  # 여러 법에 존재하는 번호만
    RNG.shuffle(cand)
    for num in cand[:args.per_type]:
        gold = [a.uid for a in by_num[num]]
        emit(f"제{num}조에는 어떤 내용이 규정되어 있나요?", gold, "loc_ambig", "(미상)", f"제{num}조")

    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"=== Locator Benchmark {len(rows)}문 저장: {OUT} ===")
    print("유형별:", dict(Counter(r["type"] for r in rows)))
    print("gold 평균 개수:", {t: round(sum(len(r["gold_ids"]) for r in rows if r["type"] == t)
                                      / max(1, sum(1 for r in rows if r["type"] == t)), 1)
                            for t in ("loc_single", "loc_range", "loc_ambig")})


if __name__ == "__main__":
    main()
