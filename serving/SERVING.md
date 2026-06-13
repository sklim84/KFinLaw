# 모델 서빙 레시피 (정석·재현 가능)

> 골드셋 생성기·judge·답변모델을 로컬 vLLM으로 서빙하는 표준 절차.
> 시스템 환경(torch 2.11+cu130, 깨진 flash_attn, 구버전 vLLM)을 건드리지 않고
> **전용 venv에 공식 권장 버전을 격리**한다. (원칙: [[feedback_do_it_properly]])

## 전용 venv
- 위치: `/home/work/kftc_model/kfinlaw-serve` (프로젝트 repo 밖, 학습 env 미간섭)
- 생성: `uv venv /home/work/kftc_model/kfinlaw-serve --python 3.12 && VIRTUAL_ENV=... uv pip install -U vllm`
- **핵심 버전**(시스템과 다름 — 이게 정상 작동의 이유): `serving/requirements.venv.lock`
  - **vllm 0.23.0**, **mistral-common 1.11.3** (시스템은 0.20.1 / 1.11.2 = reasoning_effort·멀티모달 버그)
  - torch 2.11.0, transformers 5.12.0, flashinfer 0.6.12, triton 3.6.0
- 재현: `VIRTUAL_ENV=<venv> uv pip install -r serving/requirements.venv.full.lock`

## 격리 필수 (안 하면 시스템 패키지 오염)
셸에 `PYTHONPATH=/home/work/.local/...`가 설정돼 있어 venv가 시스템 vllm을 import한다.
**반드시** `env -u PYTHONPATH PYTHONNOUSERSITE=1`로 실행 → venv 자기 패키지만 사용.
(이러면 깨진 시스템 flash_attn도 안 보여 스텁 불필요.)

## 서빙 (스크립트)
`scripts/serve_model.sh`가 위 격리 + 공식 플래그 + 잔여워커/shm 정리를 자동 처리.
```bash
scripts/serve_model.sh mistral    # 생성기: Mistral Small 4 (공식 플래그)
scripts/serve_model.sh gptoss     # judge: gpt-oss-120b
scripts/serve_model.sh stop       # 워커까지 깨끗이 종료
GPU_UTIL=0.26 scripts/serve_model.sh mistral   # 메모리 조정
```

### Mistral Small 4 공식 플래그 (모델카드 기준)
`--quantization fp8 --tensor-parallel-size 8 --reasoning-parser mistral`
`--tool-call-parser mistral --enable-auto-tool-choice --limit-mm-per-prompt '{"image":0}'`
- `--reasoning-parser mistral`: reasoning_effort per-request 파라미터 처리(없으면 토크나이저 에러)
- `--limit-mm-per-prompt '{"image":0}'`: 멀티모달(Pixtral) 더미 프로파일링 회피(텍스트 전용)
- **요청 시 `reasoning_effort="none"`** (빠르고 결정론적, 골드셋 생성에 적합)

## 학습 작업과 GPU 공존
학습이 GPU당 ~47-56GB 점유 → 여유 ~20-30GB. 그래서:
- **FP8 양자화**(가중치 ~14.6GB/GPU) + **`--gpu-memory-utilization 0.26`**(=20.6GB, 가중치+KV)
- `--max-model-len 4096 --enforce-eager` (KV·메모리 절감)
- util은 가장 빡빡한 GPU 여유에 맞춰 조정(여유<20GB면 0.24로 낮춤)

## 역할별 모델 (오염 회피)
- 생성기: **Mistral Small 4** (독립 계열, 한국어 우수 — 별표도 한국어 유지)
- judge: **gpt-oss-120b** (독립, Mistral·답변모델과 다른 계열)
- 답변모델(레이어2): A.X-4.0 / Solar-Open / EXAONE-4.0 / Gemma 4 / Qwen3.6
- ⚠️ Mistral·gpt-oss 120B는 동시 서빙이 메모리상 불가 → judge는 별도 단계(2-phase) 또는 일관성 필터로 대체

## 검증된 작동 (2026-06-13)
Mistral Small 4: 공식 채팅 엔드포인트 + `reasoning_effort="none"` 정상, 한국어 격식/구어 JSON 생성 확인.
