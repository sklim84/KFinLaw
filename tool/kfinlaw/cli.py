"""KFinLaw CLI — 터미널에서 한국 금융 법령을 조회한다(목적2).

MCP 서버(server.py)와 동일한 lawapi 코어를 재사용한다. 결과는 사람이 읽기 좋은
형식으로 출력하고, --json을 주면 스크립트·파이프라인용 JSON으로 출력한다.

실행:  LAW_OC=<인증키> kfinlaw <명령> ...   (또는 python -m kfinlaw.cli)
예:    kfinlaw article 은행법 제1조
       kfinlaw search 전자금융 --json | jq .
"""
from __future__ import annotations

import argparse
import json
import sys

from . import lawapi as L


def _out(data, as_json: bool, render):
    """as_json이면 JSON, 아니면 render(data)를 사람이 읽기 좋게 출력."""
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        render(data)


def _rows(items, cols):
    """[{...}] 를 'k: v · k: v' 줄들로 출력."""
    if not items:
        print("(결과 없음)")
        return
    for it in items:
        print(" · ".join(f"{c}={it.get(c, '')}" for c in cols))


def cmd_search(a):
    r = L.search_law(a.query, financial=not a.all)
    _out(r, a.json, lambda d: _rows(d, ["법령명", "법령ID", "MST", "시행일자", "현행", "금융코퍼스"]))


def cmd_article(a):
    r = L.get_article(a.law, a.article, effective_date=a.date or None)
    def render(d):
        print(f"[{d['법령명']}] {d['조']} {d['조문제목']}  (시행 {d.get('조문시행일자') or d.get('시행일자')})")
        print(d["본문"])
    _out(r, a.json, render)


def cmd_versions(a):
    r = L.search_eflaw(a.law)
    _out(r, a.json, lambda d: _rows(d, ["시행일자", "현행", "MST", "법령명"]))


def cmd_byeolpyo(a):
    r = L.search_byeolpyo(a.query)
    _out(r, a.json, lambda d: _rows(d, ["별표명", "별표종류", "관련법령", "파일링크"]))


def cmd_admrul(a):
    r = L.search_admrul(a.query)
    _out(r, a.json, lambda d: _rows(d, ["행정규칙명", "종류", "소관부처", "시행일자", "ID"]))


def cmd_admrul_text(a):
    r = L.get_admrul(a.id, article_no=a.article or "")
    def render(d):
        head = f"[{d['행정규칙명']}]" + (f" {d['조']}" if d.get("조") else "")
        print(f"{head}  ({d.get('소관부처')}, 시행 {d.get('시행일자')})")
        print(d["본문"])
    _out(r, a.json, render)


def cmd_term(a):
    r = L.get_term(a.term)
    def render(d):
        if not d:
            print("(정의 없음)")
            return
        for t in d:
            print(f"{t['용어']}: {t['정의']}\n  — 출처: {t['출처']}")
    _out(r, a.json, render)


def cmd_delegation(a):
    r = L.trace_delegation(a.law, a.article)
    def render(d):
        print(f"[{d['법령']}] {d['조']} 위임 단서:")
        for c in d["위임단서"] or []:
            print(f"  - {c['유형']}: {c['단서']}")
        print("위임 대상 후보:")
        cand = d["위임대상후보"]
        if isinstance(cand, str):
            print(f"  {cand}")
        else:
            for c in cand:
                print(f"  - [{c['종류']}] {c.get('행정규칙명') or c.get('법령명')}")
    _out(r, a.json, render)


def cmd_verify(a):
    r = L.verify_citation(a.text)
    def render(d):
        if not d["검증"]:
            print(d.get("비고", "(인용 없음)"))
            return
        for v in d["검증"]:
            print(f"{v['결과']}  — 「{v['법령']}」{(' ' + v['조문']) if v.get('조문') else ''}")
    _out(r, a.json, render)


def build_parser() -> argparse.ArgumentParser:
    # --json 을 최상위·서브명령 어느 위치에서도 받도록 공통 부모로 둔다.
    common = argparse.ArgumentParser(add_help=False)
    # default=SUPPRESS: 서브명령 앞/뒤 어디에 둬도 상위 값이 덮어쓰이지 않게 한다.
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="JSON으로 출력(스크립트·파이프라인용)")

    p = argparse.ArgumentParser(
        prog="kfinlaw", parents=[common],
        description="한국 금융 법령 CLI (국가법령정보센터 law.go.kr). 인증키는 환경변수 LAW_OC.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, help):
        return sub.add_parser(name, parents=[common], help=help)

    s = add("search", "법령 검색(금융 코퍼스 우선)")
    s.add_argument("query"); s.add_argument("--all", action="store_true", help="금융 우선정렬 해제(전체)")
    s.set_defaults(func=cmd_search)

    s = add("article", "법령명+조번호 → 조문 본문")
    s.add_argument("law"); s.add_argument("article")
    s.add_argument("--date", help="시행일(YYYYMMDD) 시점 버전")
    s.set_defaults(func=cmd_article)

    s = add("versions", "시행일 버전 목록")
    s.add_argument("law"); s.set_defaults(func=cmd_versions)

    s = add("byeolpyo", "별표·서식 검색")
    s.add_argument("query"); s.set_defaults(func=cmd_byeolpyo)

    s = add("admrul", "행정규칙(감독규정) 검색")
    s.add_argument("query"); s.set_defaults(func=cmd_admrul)

    s = add("admrul-text", "행정규칙 본문(--article로 특정 조)")
    s.add_argument("id"); s.add_argument("--article", help="예: 제3조")
    s.set_defaults(func=cmd_admrul_text)

    s = add("term", "법령용어 정의")
    s.add_argument("term"); s.set_defaults(func=cmd_term)

    s = add("delegation", "조문의 위임(시행령·감독규정) 추적")
    s.add_argument("law"); s.add_argument("article")
    s.set_defaults(func=cmd_delegation)

    s = add("verify", "「법령명」 제N조 인용 실재 검증")
    s.add_argument("text"); s.set_defaults(func=cmd_verify)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.json = getattr(args, "json", False)  # SUPPRESS로 미설정 시 기본 False
    try:
        args.func(args)
    except L.LawAPIError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
