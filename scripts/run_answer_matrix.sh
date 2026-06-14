#!/usr/bin/env bash
# 레이어2 답변 평가 매트릭스 — judge(gpt-oss-120b, GPU0-3:8001)는 상시 유지,
# 답변모델만 GPU4-7:8000에서 순차 교체하며 240문 평가. GPU4-7 PID만 종료해 judge 보존.
# 전제: judge가 이미 8001에 서빙 중. 실행: scripts/run_answer_matrix.sh (백그라운드 권장)
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLLM=/home/work/kftc_model/kfinlaw-serve/bin/vllm
PY=/home/work/kftc_model/_bfcl_env/bin/python
LOG="$ROOT/tests/vllm/answer.log"

# "모델:gpu_util" — 큰 모델은 util 상향(KV 확보)
MODELS=(
  "LGAI-EXAONE/EXAONE-4.0-32B:0.6"
  "Qwen/Qwen3.6-27B:0.6"
  "google/gemma-4-31B-it:0.6"
  "skt/A.X-4.0:0.8"
  "upstage/Solar-Open-100B:0.85"
)

stop_answer() {  # GPU4-7 사용 PID만 종료(judge는 GPU0-3이라 보존)
  for g in 4 5 6 7; do
    nvidia-smi -i "$g" --query-compute-apps=pid --format=csv,noheader 2>/dev/null
  done | grep -E '^[0-9]+$' | sort -u | xargs -r kill -9 2>/dev/null
  sleep 15
}

serve_answer() {  # $1=model $2=util
  env -u PYTHONPATH PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=4,5,6,7 \
    setsid nohup "$VLLM" serve "$1" --tensor-parallel-size 4 --max-model-len 8192 \
    --gpu-memory-utilization "$2" --enforce-eager --port 8000 > "$LOG" 2>&1 &
}

wait_ready() {  # 8000 준비 폴링(최대 ~13분)
  for _ in $(seq 1 40); do
    curl -s --max-time 4 http://localhost:8000/v1/models 2>/dev/null | grep -q '"id"' && return 0
    grep -qiE "out of memory|No module|ValueError: Free memory|Engine core init.*failed" "$LOG" 2>/dev/null && return 1
    sleep 20
  done
  return 1
}

echo "=== 답변 평가 매트릭스 시작: ${#MODELS[@]}개 모델 ==="
for entry in "${MODELS[@]}"; do
  model="${entry%:*}"; util="${entry##*:}"
  echo ""; echo "########## $model (util=$util) ##########"; date "+%H:%M:%S"
  stop_answer
  serve_answer "$model" "$util"
  if ! wait_ready; then
    echo "!!! $model 서빙 실패 — 건너뜀 (로그 $LOG 끝부분)"; tail -3 "$LOG"
    continue
  fi
  echo ">>> 서빙 OK, 평가 시작"
  "$PY" -m benchmark.answer_runner \
    --base-url http://localhost:8000/v1 --answer-model "$model" \
    --judge-base-url http://localhost:8001/v1 --judge-model openai/gpt-oss-120b \
    --judge-reasoning-effort low --workers 16 --retrieval good \
    2>&1 | grep -vE "^INFO|nano-vectordb|^WARNING|Batches"
done
stop_answer
echo ""; echo "=== 매트릭스 완료 ==="; date "+%H:%M:%S"
