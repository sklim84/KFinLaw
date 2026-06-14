"""
임베딩 모델 (플러그인) — 변수 격리 실험 E2의 대상
sentence-transformers로 로컬 GPU 직접 로드 (vLLM 서버 불필요).
"""
import numpy as np

from common import EMBEDDER_MODELS as MODELS   # 키 → HF repo (config.yaml)

# KoE5는 비대칭 프리픽스 요구 (query:/passage:)
PREFIX = {
    "koe5": {"query": "query: ", "passage": "passage: "},
}

_cache = {}


def _load(name):
    if name not in _cache:
        from sentence_transformers import SentenceTransformer
        _cache[name] = SentenceTransformer(MODELS[name], device="cuda", trust_remote_code=True)
    return _cache[name]


class Embedder:
    def __init__(self, name, batch_size=64):
        self.name = name
        self.model = _load(name)
        self.bs = batch_size
        self.pfx = PREFIX.get(name, {})

    def _encode(self, texts, kind):
        pfx = self.pfx.get(kind, "")
        texts = [pfx + t for t in texts]
        v = self.model.encode(texts, batch_size=self.bs, normalize_embeddings=True,
                              show_progress_bar=False, convert_to_numpy=True)
        return v.astype(np.float32)

    def encode_passages(self, texts):
        return self._encode(texts, "passage")

    def encode_queries(self, texts):
        return self._encode(texts, "query")
