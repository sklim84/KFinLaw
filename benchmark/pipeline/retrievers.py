"""
검색기 (플러그인) — 실험 E3의 대상
- VectorRetriever: numpy 코사인 (정규화 임베딩 → 내적). 소규모 코퍼스에 faiss 불필요.
- BM25Retriever: rank_bm25 (한국어는 문자 n-gram 토크나이즈)
- ParentDocRetriever: 자식(항) 단위로 검색 → 부모(조)로 dedup → 부모 전체 본문 반환 (small-to-big)
계약: retriever.search(query, top_k) -> [(chunk_dict, score), ...]  (chunk_dict.source_uids로 채점)
"""
import re
import numpy as np

from benchmark.common import CONFIG

_RET = CONFIG["retrieval"]            # rrf_k, fanout, rerank_candidates
_RERANKER_MODEL = CONFIG["models"]["reranker"]


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


class HybridRetriever:
    """BM25(어휘) + Vector(의미)를 RRF(Reciprocal Rank Fusion)로 융합.
    score(d) = Σ_r 1/(k_rrf + rank_r(d)). 법령RAG의 BM25·dense 상호보완을 결합."""
    def __init__(self, chunks, embedder, top_k=10,
                 k_rrf=_RET["rrf_k"], fanout=_RET["fanout"]):
        self.bm25 = BM25Retriever(chunks, top_k=fanout)
        self.vector = VectorRetriever(chunks, embedder, top_k=fanout)
        self.top_k, self.k_rrf, self.fanout = top_k, k_rrf, fanout

    def search(self, query, top_k=None):
        k = top_k or self.top_k
        fused, cmap = {}, {}
        for ranked in (self.bm25.search(query, self.fanout),
                       self.vector.search(query, self.fanout)):
            for rank, (chunk, _) in enumerate(ranked, 1):
                cid = chunk["chunk_id"]
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (self.k_rrf + rank)
                cmap[cid] = chunk
        order = sorted(fused.items(), key=lambda x: -x[1])[:k]
        return [(cmap[cid], sc) for cid, sc in order]


class Reranker:
    """크로스인코더 재순위(bge-reranker-v2-m3). 기저 검색기 top-N 후보를 (질의,청크)
    쌍으로 점수화해 재정렬. 정밀도·MRR 개선 목적."""
    _cache = {}

    def __init__(self, base, model_name=_RERANKER_MODEL, top_k=10,
                 candidates=_RET["rerank_candidates"]):
        if model_name not in Reranker._cache:
            from sentence_transformers import CrossEncoder
            Reranker._cache[model_name] = CrossEncoder(model_name, device="cuda",
                                                       trust_remote_code=True)
        self.ce = Reranker._cache[model_name]
        self.base, self.top_k, self.candidates = base, top_k, candidates

    def search(self, query, top_k=None):
        k = top_k or self.top_k
        cand = self.base.search(query, self.candidates)
        if not cand:
            return []
        scores = self.ce.predict([(query, c["text"]) for c, _ in cand])
        ranked = sorted(zip((c for c, _ in cand), scores), key=lambda x: -float(x[1]))
        return [(c, float(s)) for c, s in ranked[:k]]


class HyPERetriever:
    """HyPE: 청크 원문 대신 '가설 질문'들을 임베딩해 색인. 질의(질문)↔가설질문 매칭 후
    원본 청크로 역매핑·dedup. 격식 조문↔구어 질문 어휘격차 해소가 목적.
    hype_questions: {chunk_id: [질문...]}. 질문 없는 청크는 원문으로 폴백(하이브리드 색인)."""
    def __init__(self, chunks, embedder, hype_questions, top_k=10, include_raw=False):
        # include_raw=True: 가설질문 + 원문 청크 둘 다 색인(coverage gap 완화, 하이브리드 색인)
        self.embedder = embedder
        self.top_k = top_k
        texts, self.owner = [], []   # 각 벡터 → 소속 chunk
        for c in chunks:
            qs = hype_questions.get(c["chunk_id"]) or []
            if qs:
                for q in qs:
                    texts.append(q); self.owner.append(c)
                if include_raw:
                    texts.append(c["text"]); self.owner.append(c)
            else:
                texts.append(c["text"]); self.owner.append(c)  # 폴백
        self.mat = embedder.encode_passages(texts)

    def search(self, query, top_k=None):
        k = top_k or self.top_k
        q = self.embedder.encode_queries([query])[0]
        scores = self.mat @ q
        order = np.argsort(-scores)
        out, seen = [], set()
        for i in order:
            c = self.owner[int(i)]
            cid = c["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            out.append((c, float(scores[i])))
            if len(out) >= k:
                break
        return out


class HyDERetriever:
    """HyDE(Gao et al. 2023): 질문 대신 LLM이 생성한 '가설 답변'을 임베딩해 dense 검색.
    질의↔조문 어휘격차를 질의측에서 보정(HyPE=색인측의 대칭). base는 dense 기반(Vector/Hybrid),
    hyde_docs={question: 가설답변}. 캐시에 없으면 원 질문으로 폴백.
    (리랭커와 조합 시 Reranker가 base로 이걸 감싸 검색은 HyDE로, 재순위 점수는 원 질문으로 계산.)"""
    def __init__(self, base, hyde_docs, top_k=10):
        self.base, self.hyde_docs, self.top_k = base, hyde_docs, top_k

    def search(self, query, top_k=None):
        doc = self.hyde_docs.get(query) or query
        return self.base.search(doc, top_k or self.top_k)


def build_retriever(kind, chunks, embedder=None, top_k=10):
    if kind == "vector":
        return VectorRetriever(chunks, embedder, top_k)
    if kind == "bm25":
        return BM25Retriever(chunks, top_k)
    if kind == "hybrid":
        return HybridRetriever(chunks, embedder, top_k)
    raise ValueError(f"unknown retriever: {kind}")
