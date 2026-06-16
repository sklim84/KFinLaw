#!/usr/bin/env bash
# 리랭커 비교 — 하이브리드(BM25+KURE) 기저에 리랭커만 교체해 세 벤치마크 전반 평가.
# 기준 bge-reranker-v2-m3 리포트는 이미 보유 → 신규 3종만 실행.
# GPU 8장 유휴 대기 후 GPU1~7 병렬. LLM 불요(크로스인코더만).
# 실행: nohup scripts/run_reranker_compare.sh > tests/vllm/reranker.log 2>&1 &
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/work/kftc_model/_bfcl_env/bin/python
LOGD="$ROOT/tests/vllm"; mkdir -p "$LOGD"
cd "$ROOT"
flt() { grep -vE "^INFO|nano-vectordb|^WARNING|Batches|HTTP Request"; }

RERANKERS=("Dongjin-kr/ko-reranker" "upskyy/ko-reranker-8k" "BAAI/bge-reranker-large")
# 벤치마크: "라벨인자|골드셋"
BENCH=( "|benchmark/goldset/questions.jsonl" \
        "--label lowoverlap|benchmark/goldset/questions_lowoverlap.jsonl" \
        "--label locator|benchmark/goldset/questions_locator.jsonl" )

echo "=== GPU 8장 유휴 대기 $(date +%T) ==="
ok=0
while true; do
  maxu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)
  if [ "$maxu" -lt 1500 ]; then ok=$((ok+1)); else ok=0; fi
  [ "$ok" -ge 2 ] && { echo "유휴 확인(max ${maxu}MiB) $(date +%T)"; break; }
  sleep 60
done

PIDS=(); g=1
run() { local tag="$1"; shift
  CUDA_VISIBLE_DEVICES="$g" "$PY" -m benchmark.retrieval_runner \
    --chunker article --retriever hybrid --embedder kure-v1 --rerank --byeolpyo md "$@" \
    > "$LOGD/rr_${tag}.log" 2>&1 &
  PIDS+=($!); echo "  [GPU $g] $tag (pid $!)"; g=$((g%7+1))
}
echo "=== 리랭커 비교 병렬 실행 $(date +%T) ==="
for rr in "${RERANKERS[@]}"; do
  short="${rr##*/}"
  for b in "${BENCH[@]}"; do
    lbl="${b%%|*}"; gold="${b##*|}"; bname=$(basename "$gold" .jsonl)
    run "${short}_${bname}" --reranker "$rr" --goldset "$gold" $lbl
  done
done
fail=0; for p in "${PIDS[@]}"; do wait "$p" || fail=$((fail+1)); done
echo "=== 완료 $(date +%T) | 실패 $fail ==="
ls "$ROOT"/benchmark/reports/*_rr-*.json 2>/dev/null | xargs -n1 basename