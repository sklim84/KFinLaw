#!/usr/bin/env bash
# Locator Benchmark 검색 평가 — base 검색기 × 리랭커 (증강은 무관해 제외).
# GPU 8장 유휴 대기 후 GPU1~5 병렬 실행(외부 작업 비방해). LLM 불요(로컬 임베더/리랭커).
# 실행: nohup scripts/run_locator_eval.sh > tests/vllm/locator.log 2>&1 &
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/work/kftc_model/_bfcl_env/bin/python
GOLD="$ROOT/benchmark/goldset/questions_locator.jsonl"
LOGD="$ROOT/tests/vllm"; mkdir -p "$LOGD"
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

PIDS=()
run() {  # $1=gpu $2=tag rest=args
  local dev="$1" tag="$2"; shift 2
  CUDA_VISIBLE_DEVICES="$dev" "$PY" -m benchmark.retrieval_runner \
    --goldset "$GOLD" --label locator --byeolpyo md "$@" > "$LOGD/loc_${tag}.log" 2>&1 &
  PIDS+=($!); echo "  [GPU $dev] $tag (pid $!)"
}
echo "=== Locator 평가 병렬 실행 $(date +%T) ==="
run 1 bm25          --chunker article --retriever bm25
run 2 vector        --chunker article --retriever vector --embedder kure-v1
run 3 hybrid        --chunker article --retriever hybrid --embedder kure-v1
run 4 hybrid_rerank --chunker article --retriever hybrid --embedder kure-v1 --rerank
run 5 vector_rerank --chunker article --retriever vector --embedder kure-v1 --rerank
fail=0; for p in "${PIDS[@]}"; do wait "$p" || fail=$((fail+1)); done
echo "=== 완료 $(date +%T) | 실패 $fail ==="
for t in article_bm25 article_vector_kure-v1 article_hybrid_kure-v1 article_hybrid_kure-v1_rerank article_vector_kure-v1_rerank; do
  f="$ROOT/benchmark/reports/${t}_byp-md_locator.json"
  [ -f "$f" ] && "$PY" -c "import json;d=json.load(open('$f'));o=d['overall'];bt=d['by_type'];print(f'  ${t}_locator  r@5={o[\"recall@5\"]:.3f} | single={bt.get(\"loc_single\",{}).get(\"recall@5\",0):.3f} range={bt.get(\"loc_range\",{}).get(\"recall@5\",0):.3f} ambig={bt.get(\"loc_ambig\",{}).get(\"recall@5\",0):.3f}')"
done