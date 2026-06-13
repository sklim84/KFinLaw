"""
검색기 (플러그인) — 실험 E3의 대상
- VectorRetriever: numpy 코사인 (정규화 임베딩 → 내적). 소규모 코퍼스에 faiss 불필요.
- BM25Retriever: rank_bm25 (한국어는 문자 n-gram 토크나이즈)
- ParentDocRetriever: 자식(항) 단위로 검색 → 부모(조)로 dedup → 부모 전체 본문 반환 (small-to-big)
계약: retriever.search(query, top_k) -> [(chunk_dict, score), ...]  (chunk_dict.source_uids로 채점)
"""
import re
import numpy as np


def ko_tokenize(text, ngram=2):
    """한국어 BM25용: 한글은 문자 n-gram(조사 결합에 강건), 영숫자는 단어 토큰."""
    toks = []
    for run in re.findall(r"[가-힣]+|[a-zA-Z0-9]+", text):
        if run[0].isascii():
            toks.append(run.lower())
        elif len(run) < ngram:
            toks.append(run)
        else:
            toks.extend(run[i:i + ngram] for i in range(len(run) - ngram + 1))
    return toks


class VectorRetriever:
    def __init__(self, chunks, embedder, top_k=10):
        self.chunks = chunks
        self.embedder = embedder
        self.top_k = top_k
        self.mat = embedder.encode_passages([c["text"] for c in chunks])  # (N,d) 정규화

    def search(self, query, top_k=None):
        k = top_k or self.top_k
        q = self.embedder.encode_queries([query])[0]
        scores = self.mat @ q
        idx = np.argsort(-scores)[:k]
        return [(self.chunks[int(i)], float(scores[i])) for i in idx]


class BM25Retriever:
    def __init__(self, chunks, top_k=10):
        from rank_bm25 import BM25Okapi
        self.chunks = chunks
        self.top_k = top_k
        self.bm25 = BM25Okapi([ko_tokenize(c["text"]) for c in chunks])

    def search(self, query, top_k=None):
        k = top_k or self.top_k
        scores = self.bm25.get_scores(ko_tokenize(query))
        idx = np.argsort(-scores)[:k]
        return [(self.chunks[int(i)], float(scores[i])) for i in idx]


class ParentDocRetriever:
    """small-to-big: 자식 청크(항 등)로 검색하되, 같은 부모(조)는 dedup하고
    부모 전체 본문을 반환. top_k는 '서로 다른 부모' 기준. 검색 정밀도(작은 단위) +
    맥락 완결성(큰 단위)을 동시에 취함."""
    def __init__(self, child_chunks, parent_text, base_kind, embedder=None, top_k=10, fanout=6):
        self.child = build_retriever(base_kind, child_chunks, embedder, top_k * fanout)
        self.parent_text = parent_text   # parent_uid -> 전체 조 텍스트
        self.top_k = top_k
        self.fanout = fanout

    def search(self, query, top_k=None):
        k = top_k or self.top_k
        hits = self.child.search(query, k * self.fanout)
        out, seen = [], set()
        for chunk, score in hits:
            puid = chunk["source_uids"][0]
            if puid in seen:
                continue
            seen.add(puid)
            text = self.parent_text.get(puid, chunk["text"])
            out.append(({"chunk_id": puid, "text": text, "source_uids": [puid]}, score))
            if len(out) >= k:
                break
        return out


def build_retriever(kind, chunks, embedder=None, top_k=10):
    if kind == "vector":
        return VectorRetriever(chunks, embedder, top_k)
    if kind == "bm25":
        return BM25Retriever(chunks, top_k)
    raise ValueError(f"unknown retriever: {kind}")
