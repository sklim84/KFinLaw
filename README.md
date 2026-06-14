# KA-013-KFinLaw-MCP

금융 법령을 테스트베드로 **한국어 RAG 검색 기법을 정량 비교**하고(→ 사내 규정 RAG로 전이),
**국가법령정보센터 연계 MCP/CLI**를 구축하는 KFTC 연구 과제.

`최종 업데이트 2026-06-14`

[개요](#개요) · [현황](#현황) · [핵심 결과](#핵심-결과) · [빠른 시작](#빠른-시작) · [벤치마크 설계](#벤치마크-설계) · [모델·서빙](#모델서빙) · [답변 평가](#답변-평가) · [데이터·구조](#데이터구조)

---

## 개요

| | 목적 | 방향 |
|---|---|---|
| 1 | RAG 최적화 기법 시범 — 금융 법령은 테스트베드, 적용 대상은 **사내 규정 RAG** | 기법별 비교 실험 우선. 산출물은 시스템이 아니라 **전이 가능한 기법의 정량 검증·문서화** |
| 2 | 국가법령정보센터 **MCP/CLI** (Claude 호환) | `law.go.kr` 라이브 API(검색·조문·별표·인용검증), 경량·신선도 우선 |

작업 순서는 벤치마크(목적1) → MCP/CLI(목적2). 원칙은 **정석** — 공식 레시피·재현 가능 환경, 임시 우회 지양.

---

## 현황

| 단계 | 상태 |
|---|---|
| 법령 수집 (Open API) | ✅ 2,596건 목록 / 본문 XML 2,582 |
| 금융 범위 확정 | ✅ 키워드 1차(200) + 직접참조 = 931건 |
| 별표 PDF 다운로드·변환 | ✅ 1,083개(실패 0) + kordoc 마크다운 |
| 대표 코퍼스 | ✅ 핵심 금융법 32개(13군, 조문 3,609·별표 126) |
| 골드셋 (반자동) | ✅ 240문 (Mistral Small 4 + 일관성 필터) |
| 검색 실험 E1·E2·E3·E5 | ✅ 결과 ↓ |
| E6 LightRAG 그래프 | ✅ 5개 모드 평가 완료 (결과 ↓) |
| 답변 평가 | 🟢 구현 완료, 실행 대기 |
| 목적2 MCP/CLI | ⬜ 대기 |

---

## 핵심 결과

검색 실험은 한 번에 한 변수만 바꿔 비교한다 — E1 청킹 · E2 임베딩 · E3 검색기+리랭커 · E4 별표소스 · E5 HyPE · E6 그래프.
셋업: 코퍼스 32법령(~3,251 청크), 골드셋 240문(factoid·crossref·byeolpyo·multihop 각 60), gold = 조문/별표 uid.

**리더보드** — 전체 240문, recall@5 / MRR / nDCG@10

| 구성 | recall@5 | MRR | nDCG@10 |
|---|---|---|---|
| 조청킹 + 하이브리드(BM25+KURE) + 리랭커 🏆 | **0.860** | **0.775** | **0.793** |
| 조청킹 + BM25 + 리랭커 | 0.848 | 0.765 | 0.781 |
| 조청킹 + BM25 | 0.835 | 0.707 | 0.741 |
| 조청킹 + 하이브리드(RRF) | 0.831 | 0.710 | 0.735 |
| 조청킹 + 벡터(KURE-v1) + 리랭커 | 0.808 | 0.748 | 0.751 |
| 조청킹 + 벡터(KURE-v1) | 0.767 | 0.656 | 0.672 |
| LightRAG 그래프 (naive 모드·최고) | 0.738 | 0.639 | 0.648 |
| 조청킹 + HyPE | 0.675 | 0.590 | 0.598 |
| LightRAG 그래프 (mix 모드) | 0.665 | 0.606 | 0.616 |

**실험 요약**

| 실험 | 결과 |
|---|---|
| E1 청킹 | 조(條) 단위가 BM25·벡터 양쪽 최고 (fixed는 벡터에 불리, parent-doc는 벡터 랭킹 개선) |
| E2 임베딩 | KURE-v1 > KoE5 > BGE-M3 (한국어 특화 우위) |
| E3 검색기 🏆 | 하이브리드+리랭커가 최적. 리랭커가 단일 최대 레버 — crossref 0.48 → 0.73 |
| E4 별표소스 | kordoc-md vs 평문(BM25): 별표 recall@5 **0.950 vs 0.900** — 표구조 보존이 +5pp. 단 MRR·nDCG는 동급이라 평문도 경쟁력 |
| E5 HyPE ❌ | 부정 결과: 0.675 < 원문 0.767 (가설질문이 노이즈, crossref 붕괴) |
| E6 LightRAG ❌ | 그래프 RAG가 하이브리드+리랭커(0.860)에 크게 미달. 최고는 naive(0.738) < 단일 벡터(0.767), 그래프 모드(local/global/hybrid/mix)는 naive보다 낮음 — crossref·multihop에도 이득 없음 |

<details>
<summary>검색기 × 질문유형 · 반직관적 발견 · 사내 전이 권고</summary>

#### 검색기 × 질문유형 (조청킹, recall@5)
| 유형 | BM25 | 벡터(KURE) | 해석 |
|---|---|---|---|
| factoid | 0.900 | 1.000 | 의미 질문은 dense 우위 |
| crossref | 0.750 | 0.483 | 법령명 어휘 매칭 → BM25 강함 (최난도) |
| byeolpyo | 0.950 | 0.883 | 별표 수치·항목 |
| multihop | 0.742 | 0.700 | 본법+시행령 2-gold |

#### LightRAG (E6) 모드별 (recall@5 / MRR / nDCG@10)
| 모드 | recall@5 | MRR | nDCG@10 |
|---|---|---|---|
| naive (벡터only) | 0.738 | 0.639 | 0.648 |
| mix | 0.665 | 0.606 | 0.616 |
| hybrid | 0.644 | 0.593 | 0.597 |
| global | 0.585 | 0.554 | 0.558 |
| local | 0.463 | 0.430 | 0.430 |

그래프 증강 모드(local/global/hybrid/mix)가 모두 naive보다 낮다 — 엔티티 그래프가 chunk recall을 오히려 희석. 교차참조·멀티홉에서도 기대한 그래프 이득이 없었다(crossref 최고 0.467 vs BM25 0.750). (LightRAG 자체 청킹 1200자 + uid 역매핑 근사로 일부 과소평가 가능하나, 격차가 커 결론은 견고.)

#### 반직관적 발견
- 구어체 ≥ 격식체로 검색이 더 쉬움 (벡터 KURE: 격식 0.733 vs 구어 1.000) — 구어가 짧고 직접적이라 의미 매칭 용이.
- 이 결과가 HyPE 무용을 예측한다 — 메울 어휘격차가 없는데 HyPE는 그 격차를 메우는 기법.
- HyPE·LightRAG 둘 다 부정 결과 — 정교한 기법(가설질문·지식그래프)이 잘 튜닝된 하이브리드+리랭커를 못 이김.
- 교훈: "가정 말고 실측". 논문상 이득이 도메인 전이가 안 됨 → 사내 규정 RAG에서도 도입 전 실측 필수.

#### 사내 규정 RAG 전이 권고
1. 조항/섹션 단위 청킹 + 하이브리드(BM25+dense) + 리랭커를 기본으로.
2. BM25는 강력한 베이스라인(규정은 명칭·번호·표 어휘 많음), dense는 의미 질문 보완, 리랭커는 거의 항상 이득.
3. 한국어 임베딩은 KURE-v1. 교차참조(규정 간 인용)는 그래프/하이브리드로 별도 보완.

</details>

---

## 빠른 시작

벤치마크는 `benchmark` 패키지 — repo 루트에서 `python -m benchmark.<모듈>`로 실행(데이터 수집기는 `python scripts/<파일>.py`).

```bash
# 1) 데이터 (대용량은 스크립트로 재생성)
export LAW_OC=<본인_인증키>                       # 국가법령정보센터 OC (발급법 ↓)
python scripts/collect_laws.py
python scripts/download_byeolpyo.py --kinds 별표

# 2) 코퍼스 + 골드셋  (vLLM 기동: scripts/serve_model.sh mistral)
python -m benchmark.corpus
python -m benchmark.goldset.build_goldset --reasoning-effort none --no-judge

# 3) 검색 실험
python -m benchmark.retrieval_runner --chunker article --retriever hybrid --rerank \
    --embedder kure-v1 --byeolpyo md              # 최적 구성 (recall@5 0.860)
python -m benchmark.retrieval_runner --chunker article --hype --embedder kure-v1 --byeolpyo md   # E5

# 4) E6 LightRAG (GPU 전용 권장 — CUDA graph + 동시성↑로 가속)
EAGER=0 GPU_UTIL=0.7 scripts/serve_model.sh mistral
python -m benchmark.lightrag_index               # 전체 색인 (가속 시 ~80분)
python -m benchmark.lightrag_eval --modes naive local global hybrid mix

# 5) 답변 평가 (답변모델 + 독립 judge 서빙 후)
python -m benchmark.answer_runner --answer-model LGAI-EXAONE/EXAONE-4.0-32B \
    --judge-base-url http://localhost:8001/v1 --judge-model openai/gpt-oss-120b
```

환경 재현: `serving/requirements.venv.full.lock` (vllm 0.23.0 등) + sentence-transformers 5.5.1 / KURE-v1.

---

## 벤치마크 설계

**코퍼스** — 핵심 금융법 32개(13군). 법↔시행령 멀티홉·별표 조회·교차참조를 모두 평가하도록 통제된 소규모 구성.

**골드셋** — 240문, 반자동.
- Mistral Small 4로 조문/별표에서 Q&A 생성 → 일관성(round-trip BM25) 필터로 채택.
- 유형 4종 균형(각 60): factoid · crossref · byeolpyo · multihop.
- factoid는 격식↔구어 30쌍(공통 gold·pair_id) → 어휘격차 짝지어 측정.
- 무결성: gold_id 300개 전부 코퍼스 존재, 멀티홉 60문은 2-gold(본법+시행령).

**비교 축** — 일변수 격리(OFAT), 질문유형·register(격식/구어)별 분해, 품질×운영비용 동시 평가.

| 축 | 변수 | 상태 |
|---|---|---|
| A 파싱 | 별표소스(kordoc-md/평문/MinerU)·노이즈 제거 | ✅ E4(md vs 평문) · MinerU 미연결 |
| B 청킹 | 조/항/고정토큰/계층(parent-doc)·브레드크럼 | ✅ E1 |
| C 임베딩 | KURE-v1/BGE-M3/KoE5 · 하이브리드 | ✅ E2 |
| D 검색 | vector / BM25 / 하이브리드(RRF) / LightRAG 그래프 | ✅ E3 · ✅ E6 |
| E 질의·색인변환 | HyPE(색인측) · HyDE(질의측) | ✅ E5(HyPE) |
| F 재순위 | bge-reranker-v2-m3 | ✅ E3 |
| G 생성 | 컨텍스트 포맷·인용 지시 | 🟢 답변 평가 |
| H 운영 | 지연·빌드시간·비용·메모리 | ✅ timing |

**메트릭** (`benchmark/eval/`)
- 검색 평가 — recall@k · precision@k · MRR · nDCG@k. gold = uid 결정론 채점.
- 답변 평가 — 인용정확도(자동) + judge 루브릭 5종 (↓ 답변 평가 절).

<details>
<summary>골드셋 방법론 근거</summary>

- 검색 골드셋은 오픈웨이트 생성기로 충분(InPars-v2 등) — gold이 ID라 LLM-judge 편향과 무관.
- 생성기·judge·답변모델을 다른 계열로 분리해 오염(preference leakage) 회피.
- 핵심 품질장치는 일관성 필터(Promptagator/InPars) — 생성 질문을 검색기에 넣어 원본 조문이 회수되는 질문만 채택.
- BM25는 구어체를 과소평가할 수 있어, factoid 쌍은 격식체로 일관성 검사하고 구어체는 같은 정답을 공유하므로 함께 채택.

</details>

---

## 모델·서빙

3개 역할을 서로 다른 계열로 분리한다(생성·judge가 답변모델과 같으면 self-enhancement·preference leakage). 전 구간 temp=0.

| 역할 | 모델 | 비고 |
|---|---|---|
| 골드셋 생성기 | Mistral Small 4 (119B) | 독립 계열, 한국어 우수(별표도 한국어 유지) |
| judge | gpt-oss-120b | 생성기·답변모델과 다른 계열 |
| 답변모델 (답변 평가) | A.X-4.0 · Solar-Open · EXAONE-4.0 · Gemma 4 · Qwen3.6 | 사내 실사용 후보(평가 대상) |

서빙은 전용 venv `/home/work/kftc_model/kfinlaw-serve`(시스템 비오염)에서 `scripts/serve_model.sh {mistral|gptoss|stop}`.

<details>
<summary>서빙 플래그·격리·GPU 설정</summary>

- 버전 박제: vllm 0.23.0 · mistral_common 1.11.3 (시스템 0.20.1/1.11.2의 reasoning_effort·멀티모달 버그 회피). `serving/requirements.venv.lock`.
- 격리: 셸 `PYTHONPATH`가 시스템 패키지를 오염시키므로 `env -u PYTHONPATH PYTHONNOUSERSITE=1` (serve_model.sh가 자동 적용 + 잔여 워커/shm 정리).
- Mistral 플래그: `--quantization fp8 --reasoning-parser mistral --tool-call-parser mistral --enable-auto-tool-choice --limit-mm-per-prompt '{"image":0}'`, 요청 시 `reasoning_effort="none"`.
- GPU: FP8 + ctx 4096 + `--gpu-memory-utilization`(학습 공존 0.26 / GPU 전용 `GPU_UTIL=0.7`). 디코딩 가속은 `EAGER=0`(CUDA graph), 기본 `EAGER=1`(enforce-eager, 메모리 절약·재현).

</details>

---

## 답변 평가

검색 평가가 "맞는 조문을 찾았는가"라면 답변 평가는 "답이 정확·충실한가". 골드셋·코퍼스·검색기를 재사용하고 생성+채점만 얹는다.

파이프라인(`benchmark/answer_runner.py`): ① 검색(최적 검색 config 고정) → ② 답변 생성(답변모델, 근거 번호 인용) → ③ 채점(judge + 자동 인용검증).
검색 config는 `config.yaml › answer_eval`에 고정해 답변모델 효과만 격리하고, `--retrieval {good,bad,none}`로 검색품질 전이·closed-book 대조를 한 러너에서 수행.

**메트릭** (`benchmark/eval/answer_metrics.py`, RAGAS 정렬)

| 메트릭 | 측정 | 채점 |
|---|---|---|
| faithfulness | 답이 회수 컨텍스트에 근거(환각 없음) | judge |
| answer correctness | 정답과 일치 | judge (레퍼런스 기반: 정답+정답조문 제공) |
| answer relevancy | 질문에 답하는가 | judge |
| completeness | 요건/항목 누락 없는가 | judge |
| context utilization | 회수 컨텍스트를 실제 활용 | judge |
| citation accuracy | 인용 조문이 gold_ids와 일치 | 자동 (LLM 불필요) |

judge는 gpt-oss-120b(답변모델과 다른 계열), temp=0. 인용정확도만 자동·객관, 나머지는 레퍼런스 기반 judge.

<details>
<summary>RAGAS 대응 · 비교 축 · 엄밀성</summary>

#### RAGAS 대응 (정렬했으나 라이브러리 비채택)
RAGAS는 RAG 평가의 사실상 표준(reference-free LLM 자동채점). 우리 메트릭은 그 분류에 의도적으로 정렬하되, gold(정답·정답조문 uid)를 보유해 레퍼런스 기반으로 더 엄밀히 채점하고 judge 계열을 강제 분리하며 조문 uid 인용검증·한국어 프롬프트를 직접 통제하기 위해 라이브러리는 쓰지 않고 직접 구현했다.

| 우리(`answer_metrics`) | RAGAS | 차이 |
|---|---|---|
| faithfulness / answer relevancy / context utilization | 동일 | 동일 개념 |
| answer correctness | answer correctness | 둘 다 레퍼런스 필요 |
| completeness | (표준 없음, context recall 근접) | 커스텀 |
| citation accuracy | (없음) | 조문 uid 일치, 자동·도메인 특화 |

검색 평가의 recall@k·nDCG는 uid 기반 결정론 채점이라 RAGAS의 LLM 판정 context precision/recall보다 객관적이다. 외부 타당성 교차검증이 필요하면 골드셋 일부에 RAGAS를 별도 비교축으로 1회 돌릴 수 있다.

#### 고유 비교 축
1. 답변모델 5종 비교 — 동일 검색·프롬프트에서 최고 RAG 답변(사내 모델 선정 근거).
2. 검색품질 → 답변품질 전이 — 하이브리드+리랭커 vs 단일 BM25 top-1.
3. closed-book 대조 — 컨텍스트 없이 vs RAG (RAG 실효·환각 누출 점검).
4. 프롬프트 변형 — 인용지시·컨텍스트 포맷·거부유도.

유형별·register별로 분해.

#### 엄밀성
- judge 독립성: 답변모델과 다른 계열(같으면 자기우대 +10~25%). 결과는 답변모델별 분리 보고.
- 레퍼런스 기반 채점: judge에 정답+정답조문 제공 → 자기지식 의존↓.
- 인간(법률가) 표본 검수 ~150문 + 일치계수(κ) 보고 (ARES/KBL 관행).
- 보류 유형: 시행일자 버전 검색(연혁 데이터 필요), no-answer(기권 메트릭 필요) — 목적2 MCP와 함께.
- 진행 시점: E6까지 검색 최적 config 확정 후 착수(검색이 흔들리면 검색·생성 효과 분리 불가).

</details>

---

## 데이터·구조

**데이터 파이프라인** (수집 → 필터 → 전처리 → 별표)
1. 수집(`collect_laws.py`): 금융 키워드 28개 → 현행 200건 → 참조 재귀 → 2,596건(XML 2,582).
2. 금융 범위: 키워드 1차 + 직접참조 = 931건(재귀로 들어온 비금융 제외).
3. 조문 전처리(`lawdoc.py`): XML → 조 단위 청크. uid = `{법령ID}-{조문번호:04d}{-가지}` / 별표 `{법령ID}-별표{번호}{-가지}`.
4. 별표: PDF가 정답(API HTML은 JS iframe이라 스크래핑 불가, 원본 HWP는 표 구조 퇴화). 변환은 kordoc(PDF 모드)가 최적(GPU 불필요, MIT), 복잡 병합셀은 MinerU 폴백. 1,083개 전수 변환.

<details>
<summary>디렉토리 구조</summary>

```
KA-013-KFinLaw-MCP/
├── README.md
├── config.yaml                    # 단일 설정 출처(서빙·모델·검색·골드셋·답변 평가)
├── scripts/
│   ├── collect_laws.py            # 법령 수집(3단계)
│   ├── download_byeolpyo.py       # 별표 PDF 전수 다운로드(멱등)
│   ├── hwp2pdf.sh                 # HWP→PDF (LibreOffice+H2Orestart)
│   └── serve_model.sh             # vLLM 서빙(venv 격리·공식 플래그·정리)
├── benchmark/                     # python -m benchmark.<모듈>
│   ├── common.py                  # config 로드 + 공유 유틸·LLM 클라이언트
│   ├── lawdoc.py · corpus.py      # 파서(조문/별표→uid) · 코퍼스 선정
│   ├── pipeline/                  # chunkers · embedders · retrievers
│   ├── eval/                      # retrieval_metrics(검색) · answer_metrics(답변)
│   ├── goldset/                   # build_goldset · questions.jsonl · spotcheck
│   ├── retrieval_runner.py        # 검색 평가
│   ├── answer_runner.py           # 답변 평가
│   ├── hype_index.py              # HyPE(E5)
│   ├── lightrag_index.py · lightrag_eval.py   # LightRAG(E6)
│   └── reports/  (gitignore)      # 실험 결과 JSON
├── serving/  requirements.venv.lock / .full.lock   # 작동 버전 박제
├── data/     (gitignore)          # raw_xml · byeolpyo_pdf · byeolpyo_md
└── tools/    (gitignore)          # LibreOffice + H2Orestart 로컬 설치
```

</details>

**데이터 소스 · 인증키** — 국가법령정보센터 Open API (https://open.law.go.kr)
- 검색 `lawSearch.do` / 본문 `lawService.do` / 별표서식 `target=licbyl`.
- 인증키(OC)는 사용자별 발급·설정(하드코딩 안 함): 회원가입 → OPEN API 신청 → 발급 → `export LAW_OC=<키>` 후 실행.
