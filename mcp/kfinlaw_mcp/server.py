"""KFinLaw MCP 서버 — 국가법령정보센터 law.go.kr 라이브 API를 Claude(MCP)에 연결.

목적2(설계→구현): 무거운 인덱싱 없이 검색·조문·별표·인용검증을 실시간 조회.
금융 특화: 감독규정(행정규칙)·법령용어·위임 체인 추적 + 금융 코퍼스 스코핑.

실행:  LAW_OC=<인증키> python mcp/server.py   (stdio MCP)
도구:  search_law · get_article · list_law_versions · get_byeolpyo
       search_admrul · get_admrul · get_term · trace_delegation · verify_citation
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import lawapi as L

mcp = FastMCP("kfinlaw")


def _safe(fn, *a, **k):
    """LawAPIError를 LLM이 읽기 좋은 에러 dict로 변환(예외 전파 대신)."""
    try:
        return fn(*a, **k)
    except L.LawAPIError as e:
        return {"error": str(e)}


# ── 법령 검색·조문 ───────────────────────────────────────────────────────
@mcp.tool()
def search_law(query: str, financial: bool = True) -> list | dict:
    """법령명/키워드로 법령을 검색해 법령명·법령ID·MST·시행일자를 돌려준다.

    financial=True(기본)면 금융 코퍼스(핵심 32개 금융법) 항목을 위로 정렬한다.
    조문 본문이 필요하면 반환된 법령명을 get_article에 넘긴다."""
    return _safe(L.search_law, query, financial=financial)


@mcp.tool()
def get_article(law_name: str, article_no: str, effective_date: str = "") -> dict:
    """법령명과 조번호로 그 조문 본문을 직접 가져온다(위치 질의의 정답 경로).

    article_no: '제5조' · '5' · '제5조의2' 등. effective_date(YYYYMMDD)를 주면
    그 시점에 시행 중이던 과거 버전에서 조회한다(미지정 시 현행)."""
    return _safe(L.get_article, law_name, article_no, effective_date=effective_date or None)


@mcp.tool()
def list_law_versions(law_name: str) -> list | dict:
    """법령의 시행일 버전 목록(시행일자 내림차순)을 돌려준다.

    개정이 잦은 금융 법령에서 '언제 시행된 어느 버전인지'를 확인하는 데 쓴다.
    특정 시점 조문은 get_article의 effective_date로 조회한다."""
    return _safe(L.search_eflaw, law_name)


# ── 별표(요율·기준) ──────────────────────────────────────────────────────
@mcp.tool()
def get_byeolpyo(query: str) -> list | dict:
    """별표·서식을 검색한다(요율표·비율·한도·기준금액·별지서식).

    금융 법령의 수치 기준(자기자본비율·수수료율 등)은 본문이 아닌 별표에 있는
    경우가 많다. 반환된 파일링크로 원문(PDF/HWP)을 받을 수 있다."""
    return _safe(L.search_byeolpyo, query)


# ── 행정규칙(금융위 감독규정·금감원 시행세칙) ────────────────────────────
@mcp.tool()
def search_admrul(query: str) -> list | dict:
    """행정규칙(고시·훈령)을 검색한다 — 금융위 감독규정·금감원 시행세칙 등.

    금융 실무 규범은 법·시행령이 아니라 감독규정에 있는 경우가 많다.
    본문은 반환된 ID를 get_admrul에 넘겨 조회한다."""
    return _safe(L.search_admrul, query)


@mcp.tool()
def get_admrul(admrul_id: str, article_no: str = "") -> dict:
    """행정규칙 본문을 조회한다. admrul_id는 search_admrul의 'ID'.

    감독규정은 방대하므로 article_no(예 '제3조')로 특정 조만 받는 것을 권장한다.
    생략하면 전문(길면 절단)."""
    return _safe(L.get_admrul, admrul_id, article_no=article_no)


# ── 법령용어 ─────────────────────────────────────────────────────────────
@mcp.tool()
def get_term(term: str) -> list | dict:
    """법령용어의 법적 정의를 조회한다(예: 부보금융회사·적기시정조치).

    금융 법령의 정의어는 일상어와 뜻이 다를 수 있어, 해석 전 정의 확인에 쓴다."""
    return _safe(L.get_term, term)


# ── 위임 체인 추적 ───────────────────────────────────────────────────────
@mcp.tool()
def trace_delegation(law_name: str, article_no: str) -> dict:
    """조문의 하위규범 위임('대통령령으로 정한다', '금융위원회가 고시한다' 등)을 탐지하고
    위임 대상(시행령·시행규칙·감독규정) 후보를 찾아준다.

    금융 규제는 법→시행령→감독규정으로 기준이 이어져, 실제 수치는 하위규범에 있다."""
    return _safe(L.trace_delegation, law_name, article_no)


# ── 인용 검증 ────────────────────────────────────────────────────────────
@mcp.tool()
def verify_citation(text: str) -> dict:
    """문장 속 법령 인용(「법령명」 제N조)을 찾아 실제로 존재하는지 검증한다.

    LLM이 지어낸(환각) 법령명·조문을 걸러낸다. 인용마다 법령 존재 여부와,
    조문이 명시됐으면 그 조문의 존재 여부·제목을 돌려준다."""
    return _safe(L.verify_citation, text)


def main():
    """콘솔 엔트리포인트(kfinlaw-mcp) · `python -m kfinlaw_mcp.server` 진입점."""
    mcp.run()


if __name__ == "__main__":
    main()
