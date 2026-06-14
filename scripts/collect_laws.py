"""
금융 법령 수집 스크립트
1단계: 금융 관련 키워드로 법령 목록 수집
2단계: 법령 본문 다운로드 및 참조 법령 추출
3단계: 참조 법령 재귀 수집
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import time
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_XML_DIR = DATA_DIR / "raw_xml"
LIST_DIR = DATA_DIR / "law_list"

# 국가법령정보센터 Open API 인증키(OC) — 사용자별로 발급받아 환경변수로 설정.
#   발급: https://open.law.go.kr (회원가입 후 OPEN API 신청)
#   사용: export LAW_OC=<본인_인증키>
OC = os.environ.get("LAW_OC", "")
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
DETAIL_URL = "https://www.law.go.kr/DRF/lawService.do"

# 금융 관련 검색 키워드
FINANCE_KEYWORDS = [
    "금융", "은행", "보험", "증권", "자본시장",
    "신용", "여신", "수신", "전자금융", "지급결제",
    "예금", "대출", "투자", "펀드", "채권추심",
    "금융위원회", "금융감독", "금융소비자",
    "외환", "환전", "핀테크", "전자화폐",
    "가상자산", "암호화폐", "상호저축",
    "신탁", "자산운용", "선물거래",
]

# 법령 참조 패턴: 「법령명」
REF_PATTERN = re.compile(r'「([^」]+)」')


def api_request(url, params, max_retries=3):
    """API 요청 with 재시도"""
    encoded = urllib.parse.urlencode(params)
    full_url = f"{url}?{encoded}"
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(full_url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                print(f"  [ERROR] {e}")
                return None


def search_laws_by_keyword(keyword, target="law"):
    """키워드로 법령 검색, 전체 페이지 순회"""
    laws = {}
    page = 1
    display = 20

    while True:
        params = {
            "OC": OC, "target": target, "type": "XML",
            "query": keyword, "display": display, "page": page,
        }
        data = api_request(SEARCH_URL, params)
        if not data or "미신청" in data:
            break

        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            break

        total = int(root.findtext("totalCnt") or "0")
        items = root.findall(".//law")

        for item in items:
            mst = item.findtext("법령일련번호")
            if mst:
                laws[mst] = {
                    "mst": mst,
                    "법령ID": item.findtext("법령ID") or "",
                    "법령명": item.findtext("법령명한글") or "",
                    "법령약칭": item.findtext("법령약칭명") or "",
                    "법령구분": item.findtext("법령구분명") or "",
                    "소관부처": item.findtext("소관부처명") or "",
                    "시행일자": item.findtext("시행일자") or "",
                    "공포일자": item.findtext("공포일자") or "",
                    "현행여부": item.findtext("현행연혁코드") or "",
                }

        if page * display >= total:
            break
        page += 1
        time.sleep(0.3)

    return laws


def download_law_xml(mst):
    """법령 본문 XML 다운로드"""
    xml_path = RAW_XML_DIR / f"{mst}.xml"
    if xml_path.exists():
        return xml_path.read_text(encoding="utf-8")

    params = {"OC": OC, "target": "law", "MST": mst, "type": "XML"}
    data = api_request(DETAIL_URL, params)

    if data and "미신청" not in data and "<?xml" in data[:100]:
        xml_path.write_text(data, encoding="utf-8")
        return data
    return None


def extract_referenced_laws(xml_text):
    """법령 본문에서 참조된 다른 법령명 추출"""
    refs = set()
    matches = REF_PATTERN.findall(xml_text)
    for m in matches:
        name = m.strip()
        # 필터: 너무 짧거나 조/항/호 참조는 제외
        if len(name) < 3:
            continue
        if name.endswith("조") or name.endswith("항") or name.endswith("호"):
            continue
        # "같은 법", "이 법" 등 제외
        if name in ("같은 법", "이 법", "해당 법률", "다른 법률"):
            continue
        refs.add(name)
    return refs


def search_law_by_name(name):
    """법령명으로 정확한 법령 검색"""
    params = {
        "OC": OC, "target": "law", "type": "XML",
        "query": name, "display": 5, "page": 1,
    }
    data = api_request(SEARCH_URL, params)
    if not data or "미신청" in data:
        return None

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    for item in root.findall(".//law"):
        found_name = item.findtext("법령명한글") or ""
        status = item.findtext("현행연혁코드") or ""
        # 현행 법령만, 이름이 일치하는 것 우선
        if found_name == name and status == "현행":
            mst = item.findtext("법령일련번호")
            return {
                "mst": mst,
                "법령ID": item.findtext("법령ID") or "",
                "법령명": found_name,
                "법령약칭": item.findtext("법령약칭명") or "",
                "법령구분": item.findtext("법령구분명") or "",
                "소관부처": item.findtext("소관부처명") or "",
                "시행일자": item.findtext("시행일자") or "",
                "공포일자": item.findtext("공포일자") or "",
                "현행여부": status,
            }

    # 정확 매치 실패 시 첫 번째 현행 법령 반환
    for item in root.findall(".//law"):
        status = item.findtext("현행연혁코드") or ""
        if status == "현행":
            mst = item.findtext("법령일련번호")
            return {
                "mst": mst,
                "법령ID": item.findtext("법령ID") or "",
                "법령명": item.findtext("법령명한글") or "",
                "법령약칭": item.findtext("법령약칭명") or "",
                "법령구분": item.findtext("법령구분명") or "",
                "소관부처": item.findtext("소관부처명") or "",
                "시행일자": item.findtext("시행일자") or "",
                "공포일자": item.findtext("공포일자") or "",
                "현행여부": status,
            }
    return None


def main():
    if not OC:
        import sys
        sys.exit("[오류] 환경변수 LAW_OC가 설정되지 않았습니다.\n"
                 "  국가법령정보센터(https://open.law.go.kr)에서 본인 인증키를 발급받아\n"
                 "  export LAW_OC=<본인_인증키> 로 설정 후 다시 실행하세요.")
    os.makedirs(RAW_XML_DIR, exist_ok=True)
    os.makedirs(LIST_DIR, exist_ok=True)

    # ===== 1단계: 키워드별 법령 목록 수집 =====
    print("=" * 60)
    print("1단계: 금융 키워드별 법령 목록 수집")
    print("=" * 60)

    all_laws = {}  # mst -> law info

    for kw in FINANCE_KEYWORDS:
        laws = search_laws_by_keyword(kw, target="law")
        new_count = sum(1 for mst in laws if mst not in all_laws)
        all_laws.update(laws)
        print(f"  [{kw}] {len(laws)}건 검색, 신규 {new_count}건 (누적: {len(all_laws)}건)")
        time.sleep(0.3)

    # 현행 법령만 필터링
    current_laws = {mst: info for mst, info in all_laws.items() if info["현행여부"] == "현행"}
    print(f"\n현행 법령: {len(current_laws)}건 / 전체: {len(all_laws)}건")

    # 1단계 결과 저장
    with open(LIST_DIR / "step1_keyword_laws.json", "w", encoding="utf-8") as f:
        json.dump(current_laws, f, ensure_ascii=False, indent=2)
    print(f"1단계 결과 저장: {LIST_DIR / 'step1_keyword_laws.json'}")

    # ===== 2단계: 본문 다운로드 및 참조 법령 추출 =====
    print("\n" + "=" * 60)
    print("2단계: 법령 본문 다운로드 및 참조 법령 추출")
    print("=" * 60)

    all_referenced_names = set()
    downloaded = 0

    for mst, info in current_laws.items():
        xml_text = download_law_xml(mst)
        if xml_text:
            downloaded += 1
            refs = extract_referenced_laws(xml_text)
            all_referenced_names.update(refs)
            info["참조법령"] = sorted(refs)
            if downloaded % 10 == 0:
                print(f"  다운로드 {downloaded}/{len(current_laws)} 완료, 참조법령 누적 {len(all_referenced_names)}건")
        time.sleep(0.3)

    print(f"\n본문 다운로드: {downloaded}건")
    print(f"참조된 법령명 (중복 제거): {len(all_referenced_names)}건")

    # 이미 수집된 법령명 목록
    collected_names = {info["법령명"] for info in current_laws.values()}

    # 새로 수집해야 할 참조 법령
    new_refs = all_referenced_names - collected_names
    print(f"신규 참조 법령 (미수집): {len(new_refs)}건")

    # ===== 3단계: 참조 법령 재귀 수집 =====
    print("\n" + "=" * 60)
    print("3단계: 참조 법령 재귀 수집")
    print("=" * 60)

    pending_refs = list(new_refs)
    searched_names = set(collected_names)  # 이미 검색한 법령명
    round_num = 0

    while pending_refs:
        round_num += 1
        print(f"\n--- 라운드 {round_num}: {len(pending_refs)}건 검색 ---")
        next_pending = []

        for ref_name in pending_refs:
            if ref_name in searched_names:
                continue
            searched_names.add(ref_name)

            result = search_law_by_name(ref_name)
            if result and result["mst"] not in current_laws:
                current_laws[result["mst"]] = result
                print(f"  + [{result['법령구분']}] {result['법령명']}")

                # 이 법령의 본문도 다운로드하여 참조 추출
                xml_text = download_law_xml(result["mst"])
                if xml_text:
                    refs = extract_referenced_laws(xml_text)
                    result["참조법령"] = sorted(refs)
                    # 새로운 참조 법령 추가
                    for r in refs:
                        if r not in searched_names:
                            next_pending.append(r)

            time.sleep(0.3)

        pending_refs = list(set(next_pending))
        print(f"  라운드 {round_num} 완료: 누적 {len(current_laws)}건, 다음 라운드 대기 {len(pending_refs)}건")

        # 무한루프 방지
        if round_num >= 5:
            print("  [INFO] 최대 재귀 라운드(5) 도달, 종료")
            break

    # ===== 최종 결과 저장 =====
    print("\n" + "=" * 60)
    print("최종 결과")
    print("=" * 60)

    # 법령 구분별 통계
    stats = {}
    for info in current_laws.values():
        kind = info.get("법령구분", "기타")
        stats[kind] = stats.get(kind, 0) + 1

    for kind, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {kind}: {count}건")
    print(f"  합계: {len(current_laws)}건")

    # 최종 목록 저장
    with open(LIST_DIR / "final_law_list.json", "w", encoding="utf-8") as f:
        json.dump(current_laws, f, ensure_ascii=False, indent=2)

    # 간단한 목록 CSV
    with open(LIST_DIR / "final_law_list.csv", "w", encoding="utf-8") as f:
        f.write("법령일련번호,법령명,법령구분,소관부처,시행일자\n")
        for mst, info in sorted(current_laws.items(), key=lambda x: x[1].get("법령명", "")):
            f.write(f"{mst},{info['법령명']},{info.get('법령구분','')},{info.get('소관부처','')},{info.get('시행일자','')}\n")

    print(f"\n저장 완료:")
    print(f"  - {LIST_DIR / 'final_law_list.json'}")
    print(f"  - {LIST_DIR / 'final_law_list.csv'}")
    print(f"  - {RAW_XML_DIR}/ ({len(list(RAW_XML_DIR.glob('*.xml')))}개 XML 파일)")


if __name__ == "__main__":
    main()
