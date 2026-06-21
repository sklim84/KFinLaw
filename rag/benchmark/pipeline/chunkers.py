"""
청킹 전략 (플러그인) — 변수 격리 실험 E1의 대상
각 청크: {chunk_id, text, source_uids:[조문 uid...]}  (recall 채점은 source_uids vs gold_ids)
브레드크럼(법령명 > 장 > 조)을 본문 앞에 붙여 임베딩 맥락 강화.
"""
import re
from pathlib import Path
from benchmark.lawdoc import load_law


def _breadcrumb(a):
    no = f"제{a.조문번호}조" + (f"의{a.가지번호}" if a.가지번호 else "")
    parts = [a.법령명]
    if a.장:
        parts.append(a.장)
    parts.append(f"{no}({a.제목})" if a.제목 else no)
    return " > ".join(parts)


def _articles(corpus):
    out = []
    for c in corpus:
        _, arts, _ = load_law(c["mst"])
        for a in arts:
            if a.is_buchik or len(a.본문) < 20:
                continue
            out.append(a)
    return out


def chunk_article(corpus):
    """조(條) 단위 — 청크 1개 = 조문 1개"""
    chunks = []
    for a in _articles(corpus):
        chunks.append({"chunk_id": a.uid, "text": f"[{_breadcrumb(a)}]\n{a.본문}",
                       "source_uids": [a.uid]})
    return chunks


def chunk_hang(corpus):
    """항 단위 — 조문을 항 경계로 분할(항 없으면 조 전체). 모두 같은 조 uid로 매핑."""
    chunks = []
    for a in _articles(corpus):
        bc = _breadcrumb(a)
        # 본문을 항 마커(①②…, 21항 이상 ㉑–㊿ 포함)로 분할
        parts = re.split(r"\n(?=\s{2}[①-⑳㉑-㊿])", a.본문)
        if len(parts) <= 1:
            chunks.append({"chunk_id": a.uid, "text": f"[{bc}]\n{a.본문}", "source_uids": [a.uid]})
        else:
            for i, p in enumerate(parts):
                if len(p.strip()) < 10:
                    continue
                chunks.append({"chunk_id": f"{a.uid}#h{i}", "text": f"[{bc}]\n{p.strip()}",
                               "source_uids": [a.uid]})
    return chunks


def chunk_fixed(corpus, size=512, overlap=64):
    """고정 토큰(근사: 문자) 분할 — 조 경계 무시. 청크가 걸친 모든 조 uid를 source로."""
    chunks = []
    for c in corpus:
        _, arts, _ = load_law(c["mst"])
        arts = [a for a in arts if not a.is_buchik and len(a.본문) >= 20]
        # 법령 전체를 조 경계 마커와 함께 이어붙이되 위치→uid 매핑 유지
        buf, spans = "", []   # spans: (start, end, uid)
        for a in arts:
            seg = f"[{_breadcrumb(a)}]\n{a.본문}\n\n"
            spans.append((len(buf), len(buf) + len(seg), a.uid))
            buf += seg
        step = size - overlap
        ci = 0
        for st in range(0, max(1, len(buf)), step):
            piece = buf[st:st + size]
            if len(piece.strip()) < 20:
                continue
            uids = sorted({uid for (s, e, uid) in spans if s < st + size and e > st})
            chunks.append({"chunk_id": f"{c['mst']}#f{ci}", "text": piece, "source_uids": uids})
            ci += 1
    return chunks


def chunk_parent(corpus):
    """계층(parent-doc)의 자식 인덱싱 = 항 단위 청크. 부모(조) 반환은 retriever(ParentDocRetriever) 책임.
    채점은 hang과 동일(source_uids=[조 uid])."""
    return chunk_hang(corpus)


REGISTRY = {
    "article": chunk_article,
    "hang": chunk_hang,
    "fixed": chunk_fixed,
    "parent": chunk_parent,
}


def byeolpyo_chunks(corpus, source="md"):
    """별표 청크 (실험 E4의 대상: 'md'=kordoc 변환 / 'plain'=별표내용 평문).
    source_uids = [별표 uid] → byeolpyo 유형 골드셋과 채점 가능. 구분='별표'만(서식 제외)."""
    chunks = []
    for c in corpus:
        _, _, byps = load_law(c["mst"])
        for b in byps:
            if b.구분 != "별표":
                continue
            if source == "md" and b.md_path:
                body = Path(b.md_path).read_text(encoding="utf-8")
            else:
                body = b.본문_평문
            if len(body.strip()) < 20:
                continue
            head = f"{b.법령명} [별표 {b.번호}] {b.제목}"
            chunks.append({"chunk_id": f"{c['mst']}_byp{b.번호}",
                           "text": f"[{head}]\n{body[:4000]}", "source_uids": [b.uid]})
    return chunks


def build_chunks(strategy, corpus, byeolpyo=None, **kw):
    """조문 청킹(strategy) + 선택적 별표 청킹(byeolpyo='md'|'plain'|None).
    byeolpyo 유형 질문을 평가하려면 byeolpyo 지정 필수."""
    chunks = REGISTRY[strategy](corpus, **kw)
    if byeolpyo:
        chunks = chunks + byeolpyo_chunks(corpus, source=byeolpyo)
    return chunks
