"""
벤치마크 대표 코퍼스 선정
- 핵심 금융 법률 + 그 시행령/시행규칙(하위법령)을 통제된 소규모 코퍼스로 구성
- 법↔시행령 멀티홉, 별표 조회, 교차참조를 모두 평가할 수 있는 구성
산출: benchmark/corpus_ids.json  (각 법령의 mst/법령ID/구분/조문수/별표수 + 역할 태그)
"""
import xml.etree.ElementTree as ET
import json
import os
from pathlib import Path

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw_xml"
OUT = Path(__file__).parent / "corpus_ids.json"

# 핵심 금융 법률(본법). 각 본법의 시행령/시행규칙은 자동 동반 수집.
CORE_LAWS = [
    "전자금융거래법",
    "자본시장과 금융투자업에 관한 법률",
    "은행법",
    "금융소비자 보호에 관한 법률",
    "금융실명거래 및 비밀보장에 관한 법률",
    "금융지주회사법",
    "여신전문금융업법",
    "보험업법",
    "신용정보의 이용 및 보호에 관한 법률",
    "대부업 등의 등록 및 금융이용자 보호에 관한 법률",
    "금융회사의 지배구조에 관한 법률",
    "예금자보호법",
    "상호저축은행법",
]
SUFFIXES = ["", " 시행령", " 시행규칙"]


def txt(e, t):
    v = e.findtext(t); return (v or "").strip()


def build_name_index():
    """법령명 -> 메타(mst, 법령ID, 구분, 조문수, 별표수)"""
    final = json.load(open(BASE / "data/law_list/final_law_list.json", encoding="utf-8"))
    idx = {}
    for mst, v in final.items():
        f = RAW / f"{mst}.xml"
        if not f.exists():
            continue
        try:
            r = ET.parse(f).getroot()
        except ET.ParseError:
            continue
        nm = r.findtext(".//법령명_한글") or v.get("법령명", "")
        idx[nm] = {
            "mst": mst,
            "법령ID": r.findtext(".//법령ID"),
            "법령명": nm,
            "법령구분": v.get("법령구분", ""),
            "조문수": len(r.findall(".//조문단위")),
            "별표수": len([u for u in r.findall(".//별표단위") if txt(u, "별표구분") == "별표"]),
        }
    return idx


def main():
    idx = build_name_index()
    corpus = []
    missing = []
    for base_name in CORE_LAWS:
        for suf in SUFFIXES:
            nm = base_name + suf
            meta = idx.get(nm)
            if not meta:
                if suf == "":
                    missing.append(nm)
                continue
            role = "본법" if suf == "" else ("시행령" if suf == " 시행령" else "시행규칙")
            corpus.append({**meta, "본법": base_name, "역할": role})

    # 통계
    n_jo = sum(c["조문수"] for c in corpus)
    n_byp = sum(c["별표수"] for c in corpus)
    json.dump(corpus, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"코퍼스 법령: {len(corpus)}건 ({len(CORE_LAWS)}개 법령군)")
    print(f"  총 조문: {n_jo} | 총 별표('별표'종): {n_byp}")
    from collections import Counter
    c = Counter(x["역할"] for x in corpus)
    print(f"  역할별: {dict(c)}")
    if missing:
        print(f"  미수집 본법: {missing}")
    print(f"저장: {OUT}")
    print("\n구성:")
    for x in corpus:
        print(f"  [{x['역할']}] {x['법령명']} (mst={x['mst']}, {x['조문수']}조, 별표{x['별표수']})")


if __name__ == "__main__":
    main()
