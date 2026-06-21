#!/usr/bin/env bash
# LightRAG 5모드를 Semantic Benchmark로 재질의(그래프 인덱스 재사용, 재색인 없음).
# Mistral(:8000) 서빙 필요. 실행: nohup scripts/run_lightrag_semantic.sh > tests/vllm/lr_sem.log 2>&1 &
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/work/kftc_model/_bfcl_env/bin/python
GOLD="$ROOT/benchmark/goldset/questions_lowoverlap.jsonl"
export GPU_UTIL="${GPU_UTIL:-0.5}"
cd "$ROOT"

echo "=== Mistral 서빙 $(date +%T) ==="
scripts/serve_model.sh mistral || { echo "❌ 서빙 실패"; exit 1; }

echo "=== LightRAG 5모드 재질의 (Semantic) $(date +%T) ==="
"$PY" -m benchmark.lightrag_eval --goldset "$GOLD" --out lightrag_eval_lowoverlap.json \
  2>&1 | grep -vE "^INFO|nano-vectordb|Batches|HTTP Request|^DEBUG"

echo "=== Mistral 종료 $(date +%T) ==="
scripts/serve_model.sh stop
ls -la "$ROOT/benchmark/reports/lightrag_eval_lowoverlap.json" 2>/dev/null && echo "✅ 완료"
