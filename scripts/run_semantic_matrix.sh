#!/usr/bin/env bash
# Semantic Benchmark 검색 매트릭스 재실험(원본 Lexical과 동일 조건: --byeolpyo md).
# GPU1~7 병렬(임베더/리랭커) + CPU 병렬(BM25). GPU0은 외부 작업 보호를 위해 미사용.
# LLM 서빙 불필요(로컬 임베더/크로스인코더만). 실행: scripts/run_semantic_matrix.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/work/kftc_model/_bfcl_env/bin/python
GOLD="$ROOT/benchmark/goldset/questions_lowoverlap.jsonl"
LOGD="$ROOT/tests/vllm"; mkdir -p "$LOGD"
cd "$ROOT"
PIDS=()
run() {  # $1=dev(gpu번호 또는 cpu) $2=tag $3...=retrieval_runner 인자
  local dev="$1" tag="$2"; shift 2
  local cvd; [ "$dev" = "cpu" ] && cvd="" || cvd="$dev"
  CUDA_VISIBLE_DEVICES="$cvd" "$PY" -m benchmark.retrieval_runner \
    --goldset "$GOLD" --label lowoverlap --byeolpyo md "$@" \
    > "$LOGD/sem_${tag}.log" 2>&1 &
  PIDS+=($!); echo "  [GPU ${dev}] ${tag} (pid $!)"
}
echo "=== Semantic 매트릭스 병렬 실행 시작 $(date +%T) ==="
# --- GPU1~7: 임베더/리랭커 사용 (7개) ---
run 1 hang_vector    --chunker hang   --retriever vector --embedder kure-v1
run 2 fixed_vector   --chunker fixed  --retriever vector --embedder kure-v1
run 3 parent_vector  --chunker parent --retriever vector --embedder kure-v1
run 4 bge-m3         --chunker article --retriever vector --embedder bge-m3
run 5 koe5           --chunker article --retriever vector --embedder koe5
run 6 bm25_rerank    --chunker article --retriever bm25   --rerank
run 7 vector_rerank  --chunker article --retriever vector --embedder kure-v1 --rerank
# --- CPU: BM25(임베더 불필요) 3개 ---
run cpu hang_bm25    --chunker hang   --retriever bm25
run cpu fixed_bm25   --chunker fixed  --retriever bm25
run cpu parent_bm25  --chunker parent --retriever bm25
echo "=== ${#PIDS[@]}개 작업 대기 중... ==="
fail=0; for p in "${PIDS[@]}"; do wait "$p" || fail=$((fail+1)); done
echo "=== 완료 $(date +%T) | 실패 ${fail} ==="
echo "Semantic 리포트 총 개수: $(ls "$ROOT"/benchmark/reports/*lowoverlap*.json 2>/dev/null | wc -l)"
for p in "$ROOT"/benchmark/reports/*lowoverlap*.json; do
  "$PY" -c "import json;d=json.load(open('$p'));import os;print(f\"  {os.path.basename('$p'):52s} r@5={d['overall']['recall@5']:.3f}\")"
done