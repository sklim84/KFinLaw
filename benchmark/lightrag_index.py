"""
LightRAG 그래프 RAG 색인·검색 (E6)
- LLM: Mistral Small 4 (vLLM, OpenAI 호환, reasoning_effort=none)
- 임베딩: KURE-v1 (sentence-transformers)
- 각 조문/별표를 개별 문서(id=uid)로 삽입 → 검색결과를 uid로 역매핑(recall 평가용)

사용:
  python benchmark/lightrag_index.py --smoke   # 2개 법령만(통합 검증)
  python benchmark/lightrag_index.py            # 전체 코퍼스 색인
"""
import sys
import argparse
import asyncio
import numpy as np
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "pipeline"))
from chunkers import build_chunks  # noqa: E402
from common import CONFIG, DEFAULT_ENDPOINT, load_json  # noqa: E402

CORPUS = load_json(HERE / "corpus_ids.json")
WORKDIR = HERE / "lightrag_storage"
BASE_URL = DEFAULT_ENDPOINT
LLM_MODEL = CONFIG["models"]["generator"]

_kure = None
def kure():
    global _kure
    if _kure is None:
        from sentence_transformers import SentenceTransformer
        _kure = SentenceTransformer(CONFIG["models"]["embedders"]["kure-v1"], device="cuda", trust_remote_code=True)
    return _kure


async def llm_func(prompt, system_prompt=None, history_messages=None, **kwargs):
    from lightrag.llm.openai import openai_complete_if_cache
    # reasoning_effort=none(빠르고 결정론적). 추출 정확성용 temp=0.
    kwargs.pop("response_format", None)
    return await openai_complete_if_cache(
        LLM_MODEL, prompt, system_prompt=system_prompt,
        history_messages=history_messages or [], base_url=BASE_URL, api_key="EMPTY",
        temperature=0.0, extra_body={"reasoning_effort": "none"}, **kwargs)


async def embed_func(texts):
    v = kure().encode(list(texts), normalize_embeddings=True, show_progress_bar=False,
                      convert_to_numpy=True, batch_size=64)
    return v.astype(np.float32)


async def make_rag():
    from lightrag import LightRAG
    from lightrag.utils import EmbeddingFunc
    from lightrag.kg.shared_storage import initialize_pipeline_status
    WORKDIR.mkdir(parents=True, exist_ok=True)
    rag = LightRAG(
        working_dir=str(WORKDIR),
        llm_model_func=llm_func,
        llm_model_max_async=CONFIG["lightrag"]["llm_max_async"],
        embedding_func=EmbeddingFunc(embedding_dim=1024, max_token_size=8192, func=embed_func),
        addon_params={"language": "Korean"},  # 엔티티/관계를 한국어로 추출(영어 추출 방지)
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


SMOKE_LAW = "금융실명거래 및 비밀보장에 관한 법률"  # 본법14+시행령16+시행규칙5 ≈ 작은 법령군


def corpus_docs(smoke=False):
    """각 조문/별표 → (uid, 텍스트). 개별 문서로 삽입해 검색결과 uid 추적."""
    corpus = [c for c in CORPUS if c.get("본법") == SMOKE_LAW] if smoke else CORPUS
    chunks = build_chunks("article", corpus, byeolpyo="md")
    docs = []
    for c in chunks:
        uid = c["source_uids"][0]
        docs.append((uid, c["text"]))
    return docs


async def main_async(args):
    rag = await make_rag()
    docs = corpus_docs(args.smoke)
    print(f"삽입 문서(조문/별표): {len(docs)}")
    ids = [d[0] for d in docs]
    texts = [d[1] for d in docs]
    # file_paths=uid → 검색 컨텍스트에서 출처 추적
    await rag.ainsert(texts, ids=ids, file_paths=ids)
    print("색인 완료. 샘플 질의 테스트:")
    from lightrag import QueryParam
    q = "금융거래의 비밀보장은 어떻게 규정되어 있나요?"
    for mode in CONFIG["lightrag"]["modes"]:
        try:
            ctx = await rag.aquery(q, param=QueryParam(mode=mode, only_need_context=True, top_k=10))
            print(f"\n--- mode={mode} (컨텍스트 앞 300자) ---")
            print(str(ctx)[:300])
        except Exception as e:
            print(f"  [{mode}] 오류: {str(e)[:100]}")
    await rag.finalize_storages()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
