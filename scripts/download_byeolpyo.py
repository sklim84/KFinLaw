"""
별표 첨부(PDF) 전수 다운로드
- 금융범위(키워드 1차 + 직접참조) 법령의 별표단위 중 '별표' 종류 PDF를 내려받음
- 멱등: 이미 받은 파일은 건너뜀 / 재시도 / 실패 로그
사용법: python scripts/download_byeolpyo.py [--kinds 별표,서식] [--limit N]
"""
import xml.etree.ElementTree as ET
import urllib.request
import json, time, argparse
from pathlib import Path

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw_xml"
LIST = BASE / "data" / "law_list"
OUT = BASE / "data" / "byeolpyo_pdf"
HOST = "https://www.law.go.kr"


def txt(e, t):
    v = e.findtext(t); return (v or "").strip()


def finance_scope():
    """키워드 1차 + 직접참조 = 금융범위 mst 집합"""
    final = json.load(open(LIST / "final_law_list.json", encoding="utf-8"))
    step1 = json.load(open(LIST / "step1_keyword_laws.json", encoding="utf-8"))
    name2mst = {v["법령명"]: k for k, v in final.items()}
    scope = set(step1)
    for mst in list(step1):
        for rn in final.get(mst, {}).get("참조법령", []):
            if rn in name2mst:
                scope.add(name2mst[rn])
    return scope


def collect_targets(kinds):
    """다운로드 대상: (mst, 법령명, 별표번호, 제목, pdf_link) 목록"""
    scope = finance_scope()
    targets = []
    for mst in scope:
        f = RAW / f"{mst}.xml"
        if not f.exists():
            continue
        try:
            r = ET.parse(f).getroot()
        except ET.ParseError:
            continue
        law = r.findtext(".//법령명_한글") or mst
        for u in r.findall(".//별표단위"):
            if txt(u, "별표구분") not in kinds:
                continue
            pdf = txt(u, "별표서식PDF파일링크")
            if not pdf:
                continue
            num = txt(u, "별표번호") or "0"
            ga = txt(u, "별표가지번호")
            key = num + (f"-{ga}" if ga and ga != "0" else "")
            targets.append((mst, law, key, txt(u, "별표제목"), pdf))
    return targets


def download(link, dest, retries=3):
    url = HOST + link
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if data[:4] == b"%PDF":
                dest.write_bytes(data)
                return True, len(data)
            return False, "not-pdf"
        except Exception as e:
            if i < retries - 1:
                time.sleep(1.0)
            else:
                return False, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kinds", default="별표")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.25)
    args = ap.parse_args()
    kinds = set(args.kinds.split(","))

    OUT.mkdir(parents=True, exist_ok=True)
    targets = collect_targets(kinds)
    if args.limit:
        targets = targets[:args.limit]

    print(f"대상 별표: {len(targets)}건 (종류={kinds})")
    ok = skip = fail = 0
    total_bytes = 0
    failures = []
    t0 = time.time()
    for i, (mst, law, key, title, link) in enumerate(targets, 1):
        dest = OUT / f"{mst}_{key}.pdf"
        if dest.exists() and dest.stat().st_size > 0:
            skip += 1
            continue
        success, info = download(link, dest)
        if success:
            ok += 1; total_bytes += info
        else:
            fail += 1
            failures.append((mst, key, title[:30], info))
        if i % 50 == 0:
            el = time.time() - t0
            print(f"  {i}/{len(targets)} | 성공{ok} 건너뜀{skip} 실패{fail} | "
                  f"{total_bytes/1e6:.1f}MB | {el:.0f}s")
        time.sleep(args.delay)

    el = time.time() - t0
    print("\n=== 완료 ===")
    print(f"성공 {ok} / 건너뜀 {skip} / 실패 {fail} / 전체 {len(targets)}")
    print(f"총 용량 {total_bytes/1e6:.1f}MB | 소요 {el:.0f}s")
    if failures:
        print(f"\n실패 {len(failures)}건:")
        for mst, key, title, err in failures[:20]:
            print(f"  {mst}_{key} | {title} | {err}")
        json.dump(failures, open(OUT / "_failures.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
