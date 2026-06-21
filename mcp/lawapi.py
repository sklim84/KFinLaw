"""국가법령정보센터 law.go.kr DRF Open API 경량 클라이언트 (목적2 MCP/CLI 공용).

- 외부 의존 없음(표준 라이브러리 urllib·xml.etree만) — 경량·신선도 우선 원칙.
- 인증키(OC)는 환경변수 LAW_OC에서 읽는다. 발급: https://open.law.go.kr
- 지원 target: law(법령)·eflaw(시행일 법령)·admrul(행정규칙)·licbyl(별표서식)·lstrm(법령용어)
"""
from __future__ import annotations

import os
import re
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

OC = os.environ.get("LAW_OC", "")
SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"

# 금융 코퍼스(목적1 32개 핵심 금융법) — search 결과의 금융 도메인 스코핑에 사용.
_CORPUS_PATH = Path(__file__).resolve().parent.parent / "rag" / "benchmark" / "corpus_ids.json"


class LawAPIError(Exception):
    """API 호출/응답 오류."""


# ── 저수준 호출 ──────────────────────────────────────────────────────────
def _request(url: str, params: dict, timeout: int = 20) -> str:
    if not OC:
        raise LawAPIError("환경변수 LAW_OC가 설정되지 않았습니다. "
                          "open.law.go.kr에서 인증키를 발급받아 export LAW_OC=<키> 하세요.")
    q = urllib.parse.urlencode({"OC": OC, "type": "XML", **params})
    try:
        with urllib.request.urlopen(f"{url}?{q}", timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — 네트워크/HTTP 오류를 단일 타입으로 래핑
        raise LawAPIError(f"API 요청 실패: {e}") from e


def _xml(text: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        raise LawAPIError(f"XML 파싱 실패: {e}\n응답 앞부분: {text[:200]}") from e


def _t(elem, tag, default="") -> str:
    if elem is None:
        return default
    v = elem.findtext(tag)
    return v.strip() if v else default


# ── 금융 코퍼스 스코핑 ───────────────────────────────────────────────────
_FIN_IDS: set[str] | None = None
_FIN_NAMES: set[str] | None = None


def _finance_scope() -> tuple[set[str], set[str]]:
    global _FIN_IDS, _FIN_NAMES
    if _FIN_IDS is None:
        try:
            corpus = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
            _FIN_IDS = {str(x.get("법령ID", "")).zfill(6) for x in corpus}
            _FIN_NAMES = {x.get("법령명", "") for x in corpus}
        except Exception:  # noqa: BLE001 — 코퍼스 없으면 스코핑만 비활성, 동작은 유지
            _FIN_IDS, _FIN_NAMES = set(), set()
    return _FIN_IDS, _FIN_NAMES


# ── 조문 번호 파싱·추출 ──────────────────────────────────────────────────
def parse_article_no(s: str) -> tuple[str, str]:
    """'제5조의2' / '5조의2' / '5-2' / '5' → (조문번호, 가지번호). 가지 없으면 ('5','')."""
    s = str(s).strip()
    m = re.search(r"제?\s*(\d+)\s*조(?:\s*의\s*(\d+))?", s)
    if m:
        return m.group(1), (m.group(2) or "")
    m = re.search(r"(\d+)\s*[-의]\s*(\d+)", s)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"(\d+)", s)
    if m:
        return m.group(1), ""
    raise LawAPIError(f"조문 번호를 해석할 수 없습니다: {s!r}")


def _flatten_unit(unit: ET.Element) -> str:
    """조문단위 → 조문내용 + 항/호/목 평문."""
    parts = [_t(unit, "조문내용")]
    for hang in unit.findall("항"):
        hv = _t(hang, "항내용")
        if hv:
            parts.append(hv)
        for ho in hang.findall("호"):
            hov = _t(ho, "호내용")
            if hov:
                parts.append("  " + hov)
            for mok in ho.findall("목"):
                mv = _t(mok, "목내용")
                if mv:
                    parts.append("    " + mv)
    return "\n".join(p for p in parts if p).strip()


# ── 법령 검색 / 본문 ─────────────────────────────────────────────────────
def search_law(query: str, financial: bool = True, display: int = 20) -> list[dict]:
    """법령명 검색 → [{법령명, 법령ID, MST, 시행일자, 현행, 금융코퍼스}]. financial=True면 금융코퍼스 우선 정렬."""
    root = _xml(_request(SEARCH_URL, {"target": "law", "query": query, "display": display}))
    fin_ids, _ = _finance_scope()
    out = []
    for law in root.findall("law"):
        lid = _t(law, "법령ID").zfill(6)
        out.append({
            "법령명": _t(law, "법령명한글"),
            "법령ID": lid,
            "MST": _t(law, "법령일련번호"),
            "시행일자": _t(law, "시행일자"),
            "현행": _t(law, "현행연혁코드"),
            "금융코퍼스": lid in fin_ids,
        })
    if financial:
        out.sort(key=lambda r: not r["금융코퍼스"])  # 금융 코퍼스 항목 먼저
    return out


def get_law_xml(mst: str) -> ET.Element:
    return _xml(_request(SERVICE_URL, {"target": "law", "MST": mst}))


def _resolve_mst(law_name: str) -> dict:
    """법령명 → 가장 적합한 법령 1건(현행 우선, 완전일치 우선)."""
    hits = search_law(law_name, financial=False, display=20)
    if not hits:
        raise LawAPIError(f"법령을 찾지 못했습니다: {law_name!r}")
    exact = [h for h in hits if h["법령명"] == law_name]
    pool = exact or hits
    cur = [h for h in pool if h["현행"] == "현행"]
    return (cur or pool)[0]


def get_article(law_name: str, article_no: str, effective_date: str | None = None) -> dict:
    """법령명 + 조번호 → 해당 조문 본문. effective_date(YYYYMMDD)면 그 시점 시행 버전에서 조회."""
    jono, ga = parse_article_no(article_no)
    if effective_date:
        ver = _eflaw_version_at(law_name, effective_date)
        mst, meta = ver["MST"], ver
    else:
        meta = _resolve_mst(law_name)
        mst = meta["MST"]
    root = get_law_xml(mst)
    name = _t(root.find(".//기본정보"), "법령명_한글") or law_name
    jo = root.find(".//조문")
    units = jo.findall("조문단위") if jo is not None else []
    for u in units:
        # 장/절 제목 행(조문여부='전문')과 부칙은 본칙 조문번호와 겹칠 수 있어 제외
        if _t(u, "조문여부") != "조문":
            continue
        if _t(u, "조문번호") == jono and _t(u, "조문가지번호") == ga:
            return {
                "법령명": name, "MST": mst,
                "조": f"제{jono}조" + (f"의{ga}" if ga else ""),
                "조문제목": _t(u, "조문제목"),
                "조문시행일자": _t(u, "조문시행일자"),
                "본문": _flatten_unit(u),
                "시행일자": meta.get("시행일자", ""),
                "현행": meta.get("현행", ""),
            }
    raise LawAPIError(f"{name}에서 제{jono}조{('의'+ga) if ga else ''}를 찾지 못했습니다.")


# ── 시행일 법령(eflaw) ───────────────────────────────────────────────────
def _eflaw_versions(law_id: str, display: int = 200) -> list[dict]:
    """법령ID의 시행일 버전 전체 → [{법령명, 법령ID, MST, 시행일자, 현행}] (시행일 내림차순).

    eflaw는 키워드 검색이 부분일치(예: '은행법'→'국민은행법')라 LID(법령ID)로 정확 조회한다."""
    root = _xml(_request(SEARCH_URL, {"target": "eflaw", "LID": law_id, "display": display}))
    out = []
    for law in root.findall("law"):
        out.append({
            "법령명": _t(law, "법령명한글"),
            "법령ID": _t(law, "법령ID").zfill(6),
            "MST": _t(law, "법령일련번호"),
            "시행일자": _t(law, "시행일자"),
            "현행": _t(law, "현행연혁코드"),
        })
    out.sort(key=lambda r: r["시행일자"], reverse=True)
    return out


def search_eflaw(law_name: str, display: int = 200) -> list[dict]:
    """법령명 → 시행일 버전 목록(시행일 내림차순). 법령명을 법령ID로 확정한 뒤 조회."""
    return _eflaw_versions(_resolve_mst(law_name)["법령ID"], display)


def _eflaw_version_at(law_name: str, date: str) -> dict:
    """date(YYYYMMDD) 시점에 시행 중이던 버전(시행일자 <= date 중 최신)."""
    vers = search_eflaw(law_name)
    if not vers:
        raise LawAPIError(f"{law_name}의 시행일 버전 목록을 찾지 못했습니다.")
    cand = [v for v in vers if v["시행일자"] and v["시행일자"] <= date]
    if not cand:
        oldest = min(vers, key=lambda v: v["시행일자"] or "99999999")["시행일자"]
        raise LawAPIError(f"{law_name}의 {date} 시점 시행 버전이 없습니다(최초 시행 {oldest}).")
    return cand[0]  # 시행일 내림차순 → 첫 항목이 해당 시점 최신


# ── 별표·서식(licbyl) ────────────────────────────────────────────────────
def search_byeolpyo(query: str, display: int = 20) -> list[dict]:
    root = _xml(_request(SEARCH_URL, {"target": "licbyl", "query": query, "display": display}))
    out = []
    for b in root.findall("licbyl"):
        out.append({
            "별표명": _t(b, "별표명"),
            "별표종류": _t(b, "별표종류"),
            "관련법령": _t(b, "관련법령명"),
            "관련법령ID": _t(b, "관련법령ID").zfill(6),
            "별표일련번호": _t(b, "별표일련번호"),
            "파일링크": _t(b, "별표서식파일링크") or _t(b, "별표서식PDF파일링크"),
        })
    return out


# ── 행정규칙(admrul) — 금융위 감독규정·금감원 시행세칙 ───────────────────
def search_admrul(query: str, display: int = 20) -> list[dict]:
    root = _xml(_request(SEARCH_URL, {"target": "admrul", "query": query, "display": display}))
    out = []
    for a in root.findall("admrul"):
        out.append({
            "행정규칙명": _t(a, "행정규칙명"),
            "종류": _t(a, "행정규칙종류"),
            "소관부처": _t(a, "소관부처명"),
            "발령일자": _t(a, "발령일자"),
            "시행일자": _t(a, "시행일자"),
            "ID": _t(a, "행정규칙일련번호"),
        })
    return out


def get_admrul(admrul_id: str, article_no: str = "", max_chars: int = 6000) -> dict:
    """행정규칙 본문. article_no(예 '제3조')를 주면 그 조문만, 없으면 전문(길면 max_chars 절단).

    감독규정은 수십~수백 조로 방대해, 보통 특정 조를 article_no로 조회하는 편이 유용하다."""
    root = _xml(_request(SERVICE_URL, {"target": "admrul", "ID": admrul_id}))
    info = root.find(".//행정규칙기본정보")
    meta = {
        "행정규칙명": _t(info, "행정규칙명"),
        "종류": _t(info, "행정규칙종류"),
        "소관부처": _t(info, "소관부처명"),
        "시행일자": _t(info, "시행일자"),
    }
    contents = [c.text.strip() for c in root.findall(".//조문내용") if c.text and c.text.strip()]
    if article_no:
        jono, ga = parse_article_no(article_no)
        for c in contents:
            ok = c.startswith(f"제{jono}조의{ga}") if ga else bool(re.match(rf"제{jono}조(?!의\d)", c))
            if ok:
                return {**meta, "조": f"제{jono}조" + (f"의{ga}" if ga else ""), "본문": c}
        raise LawAPIError(f"{meta['행정규칙명']}에서 제{jono}조{('의'+ga) if ga else ''}를 찾지 못했습니다.")
    body = "\n".join(contents)
    truncated = len(body) > max_chars
    return {**meta,
            "본문": body[:max_chars] + ("\n…(이하 생략 — article_no로 특정 조 조회 권장)" if truncated else ""),
            "절단됨": truncated}


# ── 법령용어(lstrm) ──────────────────────────────────────────────────────
def get_term(term: str) -> list[dict]:
    """법령용어 정의 조회 → [{용어, 정의, 출처}]. (lstrm 서비스는 대표 정의 1건 반환)"""
    root = _xml(_request(SERVICE_URL, {"target": "lstrm", "query": term}))
    defn = _t(root, "법령용어정의")
    if not defn:
        return []
    return [{
        "용어": _t(root, "법령용어명_한글") or term,
        "정의": defn,
        "출처": _t(root, "출처"),
    }]


# ── 위임 체인 추적 ───────────────────────────────────────────────────────
_DELEG_RULES = [
    (re.compile(r"대통령령으로"), "시행령", "{name} 시행령", "law"),
    (re.compile(r"(총리령|부령)으로"), "시행규칙", "{name} 시행규칙", "law"),
    (re.compile(r"(금융위원회|금융감독원|위원회)가?\s*(정하여\s*)?(고시|정한다)"), "행정규칙(고시)", "{base}", "admrul"),
    (re.compile(r"감독규정"), "감독규정", "{base}", "admrul"),
]


def detect_delegation(text: str) -> list[dict]:
    """조문 본문에서 하위규범 위임 문구를 탐지 → [{유형, 단서}]."""
    found = []
    for rx, kind, _tmpl, _tgt in _DELEG_RULES:
        m = rx.search(text)
        if m:
            s = max(0, m.start() - 25)
            found.append({"유형": kind, "단서": text[s:m.end() + 10].strip().replace("\n", " ")})
    return found
