"""
검색기 (플러그인) — 실험 E3의 대상
- VectorRetriever: numpy 코사인 (정규화 임베딩 → 내적). 소규모 코퍼스에 faiss 불필요.
- BM25Retriever: rank_bm25 (한국어는 공백+간이 토크나이즈)
- (LightRAG 검색기는 별도 모듈에서 추가 — 인덱싱 비용 큼)
각 검색기.search(query) -> [(chunk_idx, score), ...] top_k
"""
import re
import numpy as np


def ko_tokenize(text, ngram=2):
    """한국어 BM25용 토크나이즈: 한글은 문자 n-gram(조사 결합에 강건), 영숫자는 단어 토큰.
    조사·어미 변화로 단어 경계가 흔들리는 한국어에서 어절 토큰보다 재현율이 높음."""
    toks = []
    for run in re.findall(r"[가-힣]+|[a-zA-Z0-9]+", text):
        if run[0].isascii():
            toks.append(run.lower())
        else:
            if len(run) < ngram:
                toks.append(run)
            else:
                toks.extend(run[i:i + ngram] for i in range(len(run) - ngram + 1))
    return toks


class VectorRetriever:
    def __init__(self, chunks, embedder, top_k=10):
        self.chunks = chunks
        self.embedder = embedder
        self.top_k = top_k
        self.mat = embedder.encode_passages([c["text"] for c in chunks])  # (N, d) 정규화됨

    def search(self, query, top_k=None):
        k = top_k or self.top_k
        q = self.embedder.encode_queries([query])[0]   # (d,)
        scores = self.mat @ q                           # 코사인(정규화됨)
        idx = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in idx]


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
        return [(int(i), float(scores[i])) for i in idx]


def build_retriever(kind, chunks, embedder=None, top_k=10):
    if kind == "vector":
        return VectorRetriever(chunks, embedder, top_k)
    if kind == "bm25":
        return BM25Retriever(chunks, top_k)
    raise ValueError(f"unknown retriever: {kind}")
