#!/usr/bin/env bash
# Semantic Benchmark 답변 평가 (전체 5개 모델) — Lexical 답변평가의 대칭 실험.
#   · 검색 컨텍스트 = Semantic 최적인 '벡터+리랭커'로 고정(--ctx-retriever vector --ctx-rerank on)
#   · judge(gpt-oss-120b) GPU0-3:8001 상시 + 답변모델 GPU4-7:8000 순차 교체
#   · 출력: reports/answer_<model>_good_semantic.json
# GPU 8장이 모두 유휴가 될 때까지 대기한 뒤 시작(외부 작업 비방해).
# 실행: nohup scripts/run_answer_semantic.sh > tests/vllm/answer_semantic.log 2>&1 &
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLLM=/home/work/kftc_model/kfinlaw-serve/bin/vllm
PY=/home/work/kftc_model/_bfcl_env/bin/python
GOLD="$ROOT/benchmark/goldset/questions_lowoverlap.jsonl"
CACHE="$ROOT/benchmark/answer_ctx_cache_semantic.json"
JLOG="$ROOT/tests/vllm/judge_semantic.log"
ALOG="$ROOT/tests/vllm/answer_semantic_serve.log"
JUDGE=openai/gpt-oss-120b
cd "$ROOT"
flt() { grep -vE "^INFO|nano-vectordb|^WARNING|Batches|HTTP Request"; }

MODELS=(                          # 모델:gpu_util(TP4 GPU4-7 기준)
  "Qwen/Qwen3.6-27B:0.6" "google/gemma-4-31B-it:0.6" "LGAI-EXAONE/EXAONE-4.0-32B:0.6"
  "skt/A.X-4.0:0.8" "upstage/Solar-Open-100B:0.85"
)

wait_idle() {  # 8장 모두 memory.used < 1500MiB가 2회 연속일 때 통과(외부 작업 종료 확인)
  echo "=== GPU 8장 유휴 대기 시작 $(date +%T) ==="
  local ok=0
  while true; do
    local maxu
    maxu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)
    if [ "$maxu" -lt 1500 ]; then ok=$((ok+1)); else ok=0; fi
    [ "$ok" -ge 2 ] && { echo "유휴 확인(max ${maxu}MiB) $(date +%T)"; return 0; }
    sleep 60
  done
}

serve_on() {  # $1=devs $2=model $3=util $4=port $5=log
  env -u PYTHONPATH PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES="$1" \
    setsid nohup "$VLLM" serve "$2" --tensor-parallel-size 4 --max-model-len 8192 \
    --gpu-memory-utilization "$3" --enforce-eager --port "$4" > "$5" 2>&1 &
}
wait_ready() {  # $1=port
  for _ in $(seq 1 45); do
    curl -s --max-time 4 "http://localhost:$1/v1/models" 2>/dev/null | grep -q '"id"' && return 0
    sleep 20
  done; return 1
}
stop_devs() {  # 주어진 GPU의 compute PID 종료
  for g in $1; do nvidia-smi -i "$g" --query-compute-apps=pid --format=csv,noheader 2>/dev/null; done \
    | grep -E '^[0-9]+$' | sort -u | xargs -r kill -9 2>/dev/null; sleep 12
}

wait_idle

echo "=== judge 서빙(GPU0-3:8001) $(date +%T) ==="
serve_on 0,1,2,3 "$JUDGE" 0.8 8001 "$JLOG"
wait_ready 8001 || { echo "❌ judge 서빙 실패"; tail -3 "$JLOG"; exit 1; }

echo "=== Semantic 컨텍스트 캐시 생성(벡터+리랭커, GPU4) $(date +%T) ==="
CUDA_VISIBLE_DEVICES=4 "$PY" -m benchmark.answer_runner --retrieval good \
  --goldset "$GOLD" --ctx-retriever vector --ctx-rerank on --embedder kure-v1 \
  --context-cache "$CACHE" --build-context-only 2>&1 | flt

for entry in "${MODELS[@]}"; do
  model="${entry%:*}"; util="${entry##*:}"
  echo ""; echo "########## $model (util=$util) $(date +%T) ##########"
  stop_devs "4 5 6 7"
  serve_on 4,5,6,7 "$model" "$util" 8000 "$ALOG"
  if ! wait_ready 8000; then echo "!!! $model 서빙 실패 — 건너뜀"; tail -3 "$ALOG"; continue; fi
  echo ">>> 서빙 OK, 평가"
  "$PY" -m benchmark.answer_runner \
    --base-url http://localhost:8000/v1 --answer-model "$model" \
    --judge-base-url http://localhost:8001/v1 --judge-model "$JUDGE" \
    --judge-reasoning-effort low --workers 16 --retrieval good \
    --goldset "$GOLD" --context-cache "$CACHE" --label semantic 2>&1 | flt
done

echo "=== 정리(judge + 답변모델 종료) $(date +%T) ==="
stop_devs "0 1 2 3 4 5 6 7"
echo "=== 완료 $(date +%T) ==="
ls -la "$ROOT"/benchmark/reports/answer_*_semantic.json 2>/dev/null