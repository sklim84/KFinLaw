"""
법령 XML → 구조화 단위(조문/별표) 공유 모듈
- 골드셋 빌더와 파이프라인 파서가 공통 사용
- 정답 식별자 체계: 조문 = f"{법령ID}-{조문번호:0>4}{가지}"  (예: 010199-0005)
                     별표 = f"{법령ID}-별표{번호}"          (예: 273695-별표0001)
"""
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from dataclasses import dataclass

from benchmark.common import txt, byeolpyo_key

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw_xml"
BYP_MD = BASE / "data" / "byeolpyo_md"

REF_PATTERN = re.compile(r"「([^」]+)」")


def _article_uid(lawid, jono, ga):
    """조문 정답 식별자. 숫자 조문번호는 4자리 zero-pad(+가지), 비숫자는 원형."""
    if jono.isdigit():
        return f"{lawid}-{int(jono):04d}" + (f"-{ga}" if ga else "")
    return f"{lawid}-{jono}{ga}"


@dataclass
class Article:
    """조문 단위"""
    uid: str            # 정답 식별자 (법령ID-조문번호)
    법령ID: str
    법령명: str
    조문번호: str
    가지번호: str
    제목: str
    장: str             # 편/장/절 브레드크럼 (있으면)
    본문: str           # 조문내용 + 항/호 평탄화
    refs: list          # 본문 내 「」 참조 법령명
    is_buchik: bool     # 부칙 여부


@dataclass
class Byeolpyo:
    uid: str
    법령ID: str
    법령명: str
    번호: str
    구분: str           # 별표/서식/...
    제목: str
    관련조문: str        # "(제N조 관련)"에서 추출
    본문_평문: str       # XML 별표내용
    md_path: str         # kordoc 변환 md 경로(있으면)


def _flatten_article(elem, lawid, lawname, chapter):
    jono = txt(elem, "조문번호")
    ga = txt(elem, "조문가지번호")
    ga = ga if (ga and ga != "0") else ""
    lines = []
    body = txt(elem, "조문내용")
    if body:
        lines.append(body)
    for hang in elem.findall("항"):
        hc = txt(hang, "항내용")
        if hc:
            lines.append("  " + hc)
        for ho in hang.findall("호"):
            hco = txt(ho, "호내용")
            if hco:
                lines.append("    " + hco)
    full = "\n".join(lines)
    refs = sorted({ref.strip() for ref in REF_PATTERN.findall(full)
                   if len(ref.strip()) >= 3 and not ref.strip().endswith(("조", "항", "호"))})
    return Article(uid=_article_uid(lawid, jono, ga), 법령ID=lawid, 법령명=lawname,
                   조문번호=jono, 가지번호=ga, 제목=txt(elem, "조문제목"), 장=chapter,
                   본문=full, refs=refs, is_buchik=(txt(elem, "조문여부") == "부칙"))


def load_law(mst):
    """법령 1건 → (메타, [Article], [Byeolpyo])"""
    f = RAW / f"{mst}.xml"
    r = ET.parse(f).getroot()
    lawid = r.findtext(".//법령ID")
    lawname = r.findtext(".//법령명_한글")

    arts = []
    jo = r.find(".//조문")
    if jo is not None:
        chapter = ""
        for elem in jo.findall("조문단위"):
            # 장 구분 행: 조문여부가 '전문'이고 제목만 있는 경우 장 제목으로 추적
            if txt(elem, "조문여부") == "전문" and not elem.findall("항"):
                heading = txt(elem, "조문제목") or txt(elem, "조문내용")
                if heading and len(heading) < 40:
                    chapter = heading
                    continue
            arts.append(_flatten_article(elem, lawid, lawname, chapter))

    byps = []
    for elem in r.findall(".//별표단위"):
        # key는 다운로드/변환 파일명·uid 공통 규칙(common.byeolpyo_key). 가지가 다른 별표는
        # 서로 다른 문서이므로 uid에도 가지를 넣어야 충돌 없음(별표8 vs 별표8의2).
        key = byeolpyo_key(txt(elem, "별표번호") or "0", txt(elem, "별표가지번호"))
        title = txt(elem, "별표제목")
        related = re.search(r"제(\d+)조", title)
        md = BYP_MD / f"{mst}_{key}.md"
        byps.append(Byeolpyo(
            uid=f"{lawid}-별표{key}",
            법령ID=lawid, 법령명=lawname, 번호=key,
            구분=txt(elem, "별표구분"), 제목=title,
            관련조문=(f"제{related.group(1)}조" if related else ""),
            본문_평문=txt(elem, "별표내용"),
            md_path=str(md) if md.exists() else "",
        ))

    meta = {"mst": mst, "법령ID": lawid, "법령명": lawname}
    return meta, arts, byps


if __name__ == "__main__":
    from benchmark.common import load_json
    corpus = load_json(Path(__file__).parent / "corpus_ids.json")
    meta, arts, byps = load_law(corpus[0]["mst"])
    print(f"{meta['법령명']}: 조문 {len(arts)}, 별표 {len(byps)}")
    a = next(x for x in arts if x.refs)
    print(f"\n샘플 조문 uid={a.uid} 제목={a.제목}")
    print(a.본문[:200])
    print("refs:", a.refs)
