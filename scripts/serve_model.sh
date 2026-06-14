#!/usr/bin/env bash
# 정석 vLLM 서빙 (재현 가능) — 전용 venv 격리 + 공식 플래그 + 프로세스그룹 정리
# 사용:
#   scripts/serve_model.sh mistral   # Mistral Small 4 (생성기)
#   scripts/serve_model.sh gptoss     # gpt-oss-120b (judge)
#   scripts/serve_model.sh stop       # 깨끗이 종료(워커 포함)
#
# 학습 작업과 GPU 공존을 위해 FP8 양자화 + 낮은 gpu-memory-utilization 사용.
# 전용 venv(/home/work/kftc_model/kfinlaw-serve)를 PYTHONPATH/유저사이트 오염 없이 사용.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# config.yaml 단일 출처에서 서빙 설정 읽기(모델·venv·포트·GPU 비율)
cfg() { python3 -c "import yaml,sys;print(yaml.safe_load(open('$ROOT/config.yaml'))$1)"; }
VENV="$(cfg "['serving']['venv']")"
VLLM="$VENV/bin/vllm"
PORT="$(cfg "['serving']['port']")"
MAX_LEN="$(cfg "['serving']['max_model_len']")"
GPU_UTIL="${GPU_UTIL:-$(cfg "['serving']['gpu_util']")}"
GEN_MODEL="$(cfg "['models']['generator']")"
JUDGE_MODEL="$(cfg "['models']['judge']")"
LOGDIR="$ROOT/tests/vllm"; mkdir -p "$LOGDIR"

stop_all() {
  # vLLM 본체 + 워커(VLLM::Worker) + 엔진코어 전부 종료(잔여 누수 방지)
  ps -eo pid,cmd 2>/dev/null \
    | grep -iE "kfinlaw-serve/bin/vllm|VLLM::|EngineCore" | grep -v grep \
    | awk '{print $1}' | xargs -r kill -9 2>/dev/null
  echo "vLLM 종료 신호 전송. GPU 해제 대기..."
  for _ in $(seq 1 30); do
    n=$(ps -eo cmd 2>/dev/null | grep -c "VLLM::Worker")
    [ "$n" -le 0 ] && break
    sleep 2
  done
  echo "정리 완료."
}

serve() {
  local model="$1"; shift
  stop_all
  echo "서빙 시작: $model"
  # 격리: PYTHONPATH 제거 + 유저사이트 차단 → venv 자기 패키지만 사용
  env -u PYTHONPATH PYTHONNOUSERSITE=1 NUMEXPR_MAX_THREADS=64 OMP_NUM_THREADS=8 \
    setsid nohup "$VLLM" serve "$model" "$@" \
    --max-model-len "$MAX_LEN" --gpu-memory-utilization "$GPU_UTIL" --enforce-eager --port "$PORT" \
    > "$LOGDIR/serve.log" 2>&1 &
  echo "PID=$! 로그=$LOGDIR/serve.log"
  echo "준비 대기(최대 ~12분)..."
  for i in $(seq 1 24); do
    sleep 30
    if curl -s --max-time 5 "http://localhost:$PORT/v1/models" 2>/dev/null | grep -q '"id"'; then
      echo "✅ 준비 완료 ($((i*30))s): $(curl -s http://localhost:$PORT/v1/models | grep -oE '"id":"[^"]*"' | head -1)"
      return 0
    fi
    if grep -qiE "Engine core initialization failed|ValueError: Free memory|out of memory|AttributeError|No module" "$LOGDIR/serve.log" 2>/dev/null; then
      echo "❌ 실패:"; grep -iE "Free memory|out of memory|AttributeError|RuntimeError:|No module" "$LOGDIR/serve.log" | grep -ivE socket | tail -3
      return 1
    fi
  done
  echo "⏱ 타임아웃"; return 1
}

case "${1:-}" in
  mistral)
    serve "$GEN_MODEL" \
      --quantization fp8 --tensor-parallel-size 8 \
      --tool-call-parser mistral --enable-auto-tool-choice --reasoning-parser mistral \
      --limit-mm-per-prompt '{"image":0}' ;;
  gptoss)
    serve "$JUDGE_MODEL" --tensor-parallel-size 8 ;;
  stop) stop_all ;;
  *) echo "사용: $0 {mistral|gptoss|stop}"; exit 1 ;;
esac
