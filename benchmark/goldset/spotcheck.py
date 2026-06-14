"""
생성기 후보 스팟체크 — 동일 조문에 여러 모델로 질문 생성시켜 한국어 품질 비교.
judge/일관성 필터 없이 '생성 품질 원본'만 본다(공정 비교). 모델별 결과를 파일로 저장.

사용 (vLLM에 모델 하나 띄운 뒤):
  python benchmark/goldset/spotcheck.py --base-url http://localhost:8000/v1 \
      --model mistralai/Mistral-Small-4-119B-2603 --tag mistral4
  # 다른 모델로 바꿔 반복 → 결과 비교
  python benchmark/goldset/spotcheck.py --compare   # 저장된 결과 나란히 출력
"""
import json
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "pipeline"))
from lawdoc import load_law  # noqa: E402
import build_goldset as BG    # noqa: E402

OUTDIR = HERE / "spotcheck"
# 고정 샘플: 다양한 법령·유형. (mst, 조문번호 또는 별표여부)
SAMPLE = [
    ("280277", "art", "5"),    # 전자금융거래법 제5조(전자문서)
    ("280277", "art", "6"),    # 제6조(접근매체) — 항/호 풍부
    ("273695", "art", "9"),    # 자본시장법 제9조(정의) — 길고 복잡
    ("277247", "art", "17"),   # 금융소비자보호법
    ("273695", "byp", None),   # 자본시장법 별표 1개
]


def pick_article(mst, jono):
    _, arts, _ = load_law(mst)
    for a in arts:
        if a.조문번호 == jono and not a.가지번호:
            return a
    return None


def pick_byeolpyo(mst):
    _, _, byps = load_law(mst)
    for b in byps:
        if b.구분 == "별표" and (b.md_path or len(b.본문_평문) > 200):
            return b
    return None


def run(base_url, model, tag):
    OUTDIR.mkdir(exist_ok=True)
    out = []
    for mst, kind, jono in SAMPLE:
        if kind == "art":
            a = pick_article(mst, jono)
            if not a:
                continue
            ctx = BG.article_context(a)
            pair = BG.gen_pair(base_url, model, ctx)
            cross = BG.gen_qa(base_url, model, "crossref", ctx, "조문") if a.refs else None
            out.append({"법령": a.법령명, "조": f"제{a.조문번호}조({a.제목})",
                        "formal": (pair or {}).get("formal"),
                        "colloquial": (pair or {}).get("colloquial"),
                        "answer": (pair or {}).get("answer"),
                        "crossref": (cross or {}).get("question")})
        else:
            b = pick_byeolpyo(mst)
            if not b:
                continue
            ctx = BG.byeolpyo_context(b)
            qa = BG.gen_qa(base_url, model, "byeolpyo", ctx, "별표")
            out.append({"법령": b.법령명, "별표": b.제목[:40],
                        "byeolpyo_q": (qa or {}).get("question"),
                        "answer": (qa or {}).get("answer")})
    fp = OUTDIR / f"{tag}.json"
    json.dump({"model": model, "items": out}, open(fp, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"저장: {fp} ({len(out)}건)")
    for it in out:
        print(json.dumps(it, ensure_ascii=False, indent=2))


def compare():
    files = sorted(OUTDIR.glob("*.json")) if OUTDIR.exists() else []
    if not files:
        print("비교할 결과 없음. 먼저 --model/--tag로 생성하세요.")
        return
    data = {f.stem: json.load(open(f, encoding="utf-8")) for f in files}
    n = max(len(d["items"]) for d in data.values())
    for i in range(n):
        print("\n" + "=" * 78)
        for tag, d in data.items():
            if i >= len(d["items"]):
                continue
            it = d["items"][i]
            head = it.get("조") or it.get("별표") or "?"
            print(f"[{tag}] {it.get('법령','')} {head}")
            for k in ("formal", "colloquial", "crossref", "byeolpyo_q"):
                if it.get(k):
                    print(f"   {k}: {it[k]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model")
    ap.add_argument("--tag")
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()
    if args.compare:
        compare()
    elif args.model and args.tag:
        run(args.base_url, args.model, args.tag)
    else:
        ap.error("--model 과 --tag 가 필요합니다 (또는 --compare).")


if __name__ == "__main__":
    main()
