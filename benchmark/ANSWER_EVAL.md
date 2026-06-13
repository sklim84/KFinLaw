# 레이어2: RAG 답변 생성 평가 설계 (Answer Evaluation)

> 레이어1(검색, `runner.py`)이 "맞는 조문을 찾았는가"를 본다면, 레이어2는 그 위에서
> **답변 생성 모델이 만든 답이 정확·충실한가**를 본다. 골드셋·코퍼스·검색기를 **재사용**하고
> 답변생성 + 답변품질 채점만 얹는다. (RAGAS의 retrieval/generation 분리와 동일 구조.)

## 두 레이어 관계
```
            골드셋 questions.jsonl  {question, answer, gold_ids, type, register, pair_id}
                  │                                    │
        [레이어1 검색]  ← gold_ids 사용          [레이어2 답변]  ← question + answer 사용
        recall@k/nDCG/MRR                         faithfulness/정확성/완결성/인용
```
- **골드셋 공유**: 레이어1은 `gold_ids`(정답 조문), 레이어2는 `answer`(정답 텍스트)+`question`을 사용. 새 골드셋 불필요.
- **검색기 재사용**: 레이어2의 컨텍스트는 레이어1에서 가장 좋았던 검색 config로 회수.

## 모델 3-역할 (오염 회피, 2026-06 결정)
| 역할 | 모델 | 독립성 |
|---|---|---|
| **답변 생성(평가대상)** | A.X-4.0 · Solar-Open-100B · EXAONE-4.0-32B · Gemma 4 · Qwen3.6 (사내 실사용) | 비교대상 |
| **judge(채점)** | **gpt-oss-120b** (답변풀 밖·독립) | 답변모델과 달라야(self-enhancement 회피) |
| 골드셋 생성기 | Mistral Small 4 (답변풀 밖·독립) | judge와도 다른 계열 |
> judge가 답변모델 중 하나와 같으면 자기 답을 후하게 줌(self-enhancement, +10~25%). 반드시 분리.
> 모든 생성·채점 temp=0(재현성·법률 충실성).

## 파이프라인 (신규 `benchmark/answer_runner.py`)
질문별로:
1. **검색** — 고정 검색 config로 컨텍스트 top-k 회수 (레이어1 검색기 재사용)
2. **답변 생성** — `[지시+컨텍스트+질문]` → 답변모델 → 답변(+인용 조문)
3. **채점** — judge가 (질문, 생성답변, 정답, 회수컨텍스트, 정답조문)을 보고 점수

config 예: `{answer_model, retriever_config(레이어1 우승), top_k, prompt_variant}`

## 메트릭 (신규 `benchmark/eval/answer_metrics.py`, RAGAS 호환)
| 메트릭 | 측정 | 비고 |
|---|---|---|
| **faithfulness(충실성)** | 답이 회수 컨텍스트에 근거하는가(환각 없음) | 법률 환각 방지 핵심 |
| **answer correctness(정확성)** | 정답(`answer`)과 일치하는가 | gold 대조 |
| **answer relevancy(적합성)** | 질문에 답하는가 | |
| **completeness(완결성)** | 필요한 요건/항목을 빠짐없이 | multihop·요건 질문 |
| **citation accuracy(인용 정확도)** | 인용한 조문이 `gold_ids`와 일치하는가 | 법률 특화·자동채점 가능 |
| **context utilization** | 회수 컨텍스트를 실제로 활용했는가 | |
> citation accuracy는 LLM 없이 자동(조문번호 파싱 vs gold_ids). 나머지는 judge(gpt-oss).

## 핵심 비교 축 (레이어2 고유)
1. **답변 모델 비교** — 동일 검색·프롬프트에서 5개 모델 중 누가 최고 RAG 답변? (사내 모델 선정 근거)
2. **검색 품질 → 답변 품질 전이** — 좋은 검색 vs 나쁜 검색이 답변에 미치는 영향(레이어1↔2 연결)
3. **closed-book 대조** — 컨텍스트 없이(모델 지식만) vs RAG. RAG가 실제로 도움 되는지, 환각 누출 점검
4. **프롬프트 변형** — 인용 지시·컨텍스트 포맷·거부("근거 없으면 모른다") 유도
- 유형별(factoid/crossref/byeolpyo/multihop)·register별(격식/구어) 분해.

## 채점 방식 (judge 안정화)
- **레퍼런스 기반**: judge에 정답(`answer`)+정답조문 본문을 함께 제공 → 자기지식 의존↓, 일관성↑.
- **5점 또는 이진×다축** 루브릭, temp=0. 위치/순서 편향 회피(답변 순서 무작위화 시 시드 고정).
- 표본 **인간(법률가) 검수**로 judge 신뢰도 앵커(κ 보고) — 출판급 시.

## 산출물
- `benchmark/answer_runner.py` — config → 검색·생성·채점 → `reports/answer_{config}.json`
- `benchmark/eval/answer_metrics.py` — 위 메트릭
- 리포트: 답변모델 × 메트릭 leaderboard + 유형/register 분해 + closed-book 대비

## 진행 시점
레이어1(E1~E4 검색)로 **최적 검색 config 확정 후** 레이어2 착수(그 config를 답변 컨텍스트 소스로 고정).
검색이 흔들리면 답변 평가가 검색·생성 효과를 분리 못 하므로 순서가 중요.

## 참고
RAGAS(faithfulness·answer_relevancy·context_precision/recall) · ARES(NAACL'24) · 레이어1 축은 [AXES.md](AXES.md).
