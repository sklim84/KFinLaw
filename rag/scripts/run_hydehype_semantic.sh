#!/usr/bin/env bash
# HyDE+HyPE 중첩을 Semantic Benchmark로 평가(리더보드 보강). GPU 유휴 대기 후 2개 run.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; PY=/home/work/kftc_model/_bfcl_env/bin/python
GOLD="$ROOT/benchmark/goldset/questions_lowoverlap.jsonl"; HYDE="$ROOT/benchmark/hyde_cache_lowoverlap.json"
cd "$ROOT"; flt(){ grep -vE "^INFO|nano-vectordb|Batches|^WARNING|HTTP Request"; }
ok=0; echo "=== GPU 유휴 대기 $(date +%T) ==="
while true; do mu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits|sort -n|tail -1)
  [ "$mu" -lt 1500 ] && ok=$((ok+1)) || ok=0; [ "$ok" -ge 2 ] && break; sleep 60; done
echo "유휴 확인 $(date +%T)"
run(){ echo ">>> $*"; "$PY" -m benchmark.retrieval_runner --chunker article --retriever bm25 \
  --embedder kure-v1 --byeolpyo md --hype questions --hyde --hyde-cache "$HYDE" \
  --goldset "$GOLD" --label lowoverlap "$@" 2>&1 | flt; }
run                # 벡터+HyDE+HyPE
run --rerank       # 벡터+리랭커+HyDE+HyPE
echo "=== 완료 $(date +%T) ==="
for t in article_bm25_kure-v1_hype_hyde_byp-md_lowoverlap article_bm25_kure-v1_hype_hyde_rerank_byp-md_lowoverlap; do
  "$PY" -c "import json;print('$t', round(json.load(open('benchmark/reports/$t.json'))['overall']['recall@5'],3))"; done
