#!/usr/bin/env bash
# 증강 그리드 보강 — 리더보드의 증강(HyDE/HyPE/둘다)을 적용 가능한 모든 기저에 채움(Lexical).
# 검색 평가(결정론)라 LLM 서빙 불필요. hyde_cache.json·hype_cache.json 재사용.
# GPU 8장 유휴 대기 후 실행(외부 작업 비방해). 결과만 산출, 리더보드/figure 통합은 수동.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/work/kftc_model/_bfcl_env/bin/python
cd "$ROOT"
flt() { grep -vE "^INFO|nano-vectordb|^WARNING|Batches|HTTP Request"; }

echo "=== GPU 8장 유휴 대기 $(date +%T) ==="
ok=0
while true; do
  maxu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)
  if [ "$maxu" -lt 1500 ]; then ok=$((ok+1)); else ok=0; fi
  [ "$ok" -ge 2 ] && { echo "유휴 확인(max ${maxu}MiB) $(date +%T)"; break; }
  sleep 60
done

run() { echo ""; echo ">>> $*"; "$PY" -m benchmark.retrieval_runner \
  --chunker article --embedder kure-v1 --byeolpyo md "$@" 2>&1 | flt; }

# 신규 5개 (기존 3개: 벡터+HyDE, 하이브리드+리랭커+HyDE, 벡터+HyPE 는 보유)
run --retriever vector --hyde --rerank                 # 벡터+리랭커+HyDE
run --retriever hybrid --hyde                          # 하이브리드+HyDE
run --retriever bm25   --hype questions --rerank       # 벡터+리랭커+HyPE (HyPE는 retriever 무시)
run --retriever bm25   --hype questions --hyde         # 벡터+HyDE+HyPE
run --retriever bm25   --hype questions --hyde --rerank  # 벡터+리랭커+HyDE+HyPE

echo ""; echo "=== 완료 $(date +%T) — 신규 증강 리포트 ==="
for t in article_vector_kure-v1_hyde_rerank_byp-md article_hybrid_kure-v1_hyde_byp-md \
         article_bm25_kure-v1_hype_rerank_byp-md article_bm25_kure-v1_hype_hyde_byp-md \
         article_bm25_kure-v1_hype_hyde_rerank_byp-md; do
  f="$ROOT/benchmark/reports/$t.json"
  [ -f "$f" ] && "$PY" -c "import json;d=json.load(open('$f'));print(f'  $t  r@5={d[\"overall\"][\"recall@5\"]:.3f}')"
done