#!/usr/bin/env bash
# Semantic Benchmark 구축 + 핵심/증강 7개 config 재평가 (어휘중첩 편향 검증, README §4).
#   [1] Mistral 서빙 → Semantic 골드셋 생성(build_goldset --lowoverlap)
#   [2] Semantic용 HyDE 캐시 생성 → Mistral 종료
#   [3] 핵심 4개(bm25/vector/hybrid/hybrid+rerank) + 증강 3개(HyPE/HyDE) 재평가
# HyPE 캐시(hype_cache.json)는 색인측이라 골드셋 무관 → 재사용. HyDE 캐시만 신규 생성.
# 청킹·임베딩·리랭커 등 나머지 config은 run_semantic_matrix.sh, LightRAG는 run_lightrag_semantic.sh.
# 실행: nohup scripts/run_semantic_build.sh > tests/vllm/semantic_build.log 2>&1 &
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/work/kftc_model/_bfcl_env/bin/python
# config 기본(0.26)은 8-GPU 학습 빡빡 공존용. 여유가 크면 KV캐시 확보 위해 0.5로 상향.
export GPU_UTIL="${GPU_UTIL:-0.5}"
GOLD="$ROOT/benchmark/goldset/questions_lowoverlap.jsonl"   # lowoverlap = Semantic Benchmark 파일
HYDE="$ROOT/benchmark/hyde_cache_lowoverlap.json"
cd "$ROOT"
flt() { grep -vE "^INFO|nano-vectordb|^WARNING|Batches|HTTP Request|^Processed"; }

echo "############ [1/3] Mistral 서빙 + Semantic 골드셋 생성 ############"; date "+%F %T"
scripts/serve_model.sh mistral || { echo "❌ Mistral 서빙 실패"; exit 1; }
"$PY" -m benchmark.goldset.build_goldset --lowoverlap --reasoning-effort none 2>&1 | flt
[ -s "$GOLD" ] || { echo "❌ 골드셋 생성 실패($GOLD 없음)"; scripts/serve_model.sh stop; exit 1; }

echo "############ [2/3] Semantic HyDE 캐시 생성 ############"; date "+%F %T"
"$PY" -m benchmark.hyde_gen --reasoning-effort none --workers 16 \
  --goldset "$GOLD" --out "$HYDE" 2>&1 | flt
echo "--- Mistral 종료(검색 평가는 로컬 임베더만 사용) ---"
scripts/serve_model.sh stop

echo "############ [3/3] 핵심 4 + 증강 3 config 재평가 (label=lowoverlap) ############"; date "+%F %T"
run() { echo ""; echo ">>> $*"; "$PY" -m benchmark.retrieval_runner \
  --goldset "$GOLD" --label lowoverlap --byeolpyo md "$@" 2>&1 | flt; }
run --chunker article --retriever bm25                                          # 어휘(BM25) 기준선
run --chunker article --retriever vector --embedder kure-v1                     # dense 기준선
run --chunker article --retriever hybrid --embedder kure-v1                     # 하이브리드
run --chunker article --retriever hybrid --embedder kure-v1 --rerank            # Lexical 최고(0.860)
run --chunker article --retriever bm25   --embedder kure-v1 --hype questions    # HyPE(색인측 증강)
run --chunker article --retriever vector --embedder kure-v1 --hyde --hyde-cache "$HYDE"           # HyDE on vector
run --chunker article --retriever hybrid --embedder kure-v1 --hyde --hyde-cache "$HYDE" --rerank  # HyDE on hybrid+rerank

echo ""; echo "############ 완료 ############"; date "+%F %T"
ls -la "$ROOT"/benchmark/reports/*lowoverlap*.json
