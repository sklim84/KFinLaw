# KA-013-KFinLaw-MCP

금융결제원(KFTC) 연구 과제. **금융 법령으로 한국어 RAG 검색 기법을 정량 비교**해 최적 파이프라인을 찾고(→ 사내 규정 RAG로 전이),
**국가법령정보센터 연계 MCP/CLI**를 구축한다.
*최종 업데이트: 2026-06-14*

## 목차
1. [프로젝트 목적](#1-프로젝트-목적-두-가지)
2. [진행 현황](#2-진행-현황)
3. [🏆 핵심 결과 — 1차 검색 실험](#3--핵심-결과--1차-검색-실험)
4. [디렉토리 구조](#4-디렉토리-구조)
5. [데이터 파이프라인](#5-데이터-파이프라인)
6. [벤치마크 설계](#6-벤치마크-설계)
7. [모델 역할 & 서빙](#7-모델-역할--서빙)
8. [레이어2 — 답변 생성 평가 (설계·구현)](#8-레이어2--답변-생성-평가-설계구현)
9. [재현 방법](#9-재현-방법)
10. [데이터 소스 · 인증키](#10-데이터-소스--인증키)

---

## 1. 프로젝트 목적 (두 가지)

**목적 1 — 사내 규정 RAG 파이프라인 최적화 기법 시범**
- 금융 법령은 **테스트베드**, 최종 적용 대상은 **사내 규정 RAG**.
- 핵심 산출물 = "작동하는 시스템"이 아니라 **전이 가능한 최적화 기법의 정량 검증·문서화**.
- 방향: **기법별 비교 실험 우선**. 전수 인덱싱 불필요, 대표 샘플로 충분.

**목적 2 — 국가법령정보센터 연계 MCP/CLI (Claude 등 호환)**
- `law.go.kr` Open API 연계 **MCP 서버 + CLI**. (인증키는 사용자별 발급·설정 — §10)
- 방향: **라이브 API 연계 중심**(검색/조문/별표/인용검증), 경량·신선도 우선.

> **작업 순서**: 벤치마크 하니스(목적1) → MCP/CLI(목적2). 두 목적은 상호보완.
> **원칙**: 항상 **정석대로**(공식 레시피·재현 가능 환경·공식 템플릿, 임시 우회 지양).

---

## 2. 진행 현황

| 단계 | 상태 | 요약 |
|---|---|---|
| 법령 수집 (Open API) | ✅ | 2,596건 목록 / 본문 XML 2,582개 |
| 금융 범위 확정 | ✅ 분석 | 키워드 1차(200) + 직접참조 = 931건 |
| 별표 PDF 다운로드·변환 | ✅ | 1,083개 다운로드(실패 0) + kordoc 마크다운 변환 |
| 대표 코퍼스 | ✅ | 핵심 금융법 32개(13군, 조문 3,609 + 별표 126) |
| 골드셋 (반자동) | ✅ | **240문** (Mistral Small 4 생성 + 일관성 필터) |
| 벤치마크 하니스 | ✅ | 청커·임베더·검색기 플러그인 + 메트릭 + 러너 |
| **1차 검색 실험** (E1·E2·E3·E5) | ✅ | 청킹·임베딩·하이브리드·리랭커·HyPE (결과 §3) |
| **E6 LightRAG 그래프** | ⏸ 보류 | 통합·검증 완료, **전체 색인은 학습 GPU 종료 후 재개** |
| 레이어2 답변 평가 | 🟢 구현(실행 대기) | 아래 §8 (`answer_runner.py`·`answer_metrics.py` 완료, 답변모델 서빙 후 실행) |
| 목적2 MCP/CLI | ⬜ 대기 | 하니스 완료 후 |

---

## 3. 🏆 핵심 결과 — 1차 검색 실험

> **실험 코드**: 하나의 변수만 바꿔 비교(§6 축 A~H에 대응).
> **E1** 청킹 · **E2** 임베딩 · **E3** 검색기(하이브리드·리랭커) · **E4** 별표 소스(미실행) · **E5** HyPE · **E6** LightRAG 그래프(색인 보류).

**셋업**: 코퍼스 32법령(청크 ~3,251), 골드셋 240문(factoid/crossref/byeolpyo/multihop 각 60),
메트릭 recall@k·MRR·nDCG@10 (질문유형별·register(격식체/구어체)별 분해, gold = 조문/별표 uid). 상세 설계는 §6.

### 종합 리더보드 (전체, recall@5 / MRR / nDCG@10)
| 구성 | recall@5 | MRR | nDCG@10 |
|---|---|---|---|
| **조청킹 + 하이브리드(BM25+KURE) + 리랭커** | **0.860** | **0.775** | **0.793** 🏆 |
| 조청킹 + BM25 + 리랭커 | 0.848 | 0.765 | 0.781 |
| 조청킹 + BM25 | 0.835 | 0.707 | 0.741 |
| 조청킹 + 하이브리드(RRF) | 0.831 | 0.710 | 0.735 |
| 조청킹 + 벡터(KURE-v1) + 리랭커 | 0.808 | 0.748 | 0.751 |
| 조청킹 + 벡터(KURE-v1) | 0.767 | 0.656 | 0.672 |
| 조청킹 + HyPE | 0.675 | 0.590 | 0.598 |

### 실험별 발견
- **E1 청킹**: 조(條) 단위가 BM25·벡터 양쪽 최고. fixed는 BM25엔 좋고 벡터엔 나쁨, parent-doc는 벡터 랭킹 개선.
- **E2 임베딩**: **KURE-v1 > KoE5 > BGE-M3** (한국어 특화 우위).
- **E3 하이브리드+리랭커** 🏆: **최고 구성**. 리랭커가 단일 최대 레버(recall@1·MRR·nDCG 대폭↑). crossref 0.48→0.73.
- **E5 HyPE** ❌: **부정 결과(도움 안 됨)**. HyPE(0.675) < 원문(0.767). 가설질문이 노이즈, crossref 붕괴.
- **E6 LightRAG**: 통합 검증 완료(한국어 엔티티·교차참조 그래프 포착). 전체 색인 보류.

### 검색기·유형 상호작용 (조청킹)
| 유형 | BM25 | 벡터(KURE) | 비고 |
|---|---|---|---|
| factoid | 0.900 | **1.000** | 의미질문은 dense 우위 |
| crossref | **0.750** | 0.483 | 법령명 어휘 매칭 → BM25 강함 (최난도) |
| byeolpyo | **0.950** | 0.883 | 별표 수치·항목 |
| multihop | 0.742 | 0.700 | 본법+시행령 2-gold |

### 🔥 반직관적 발견 & 방법론 교훈
- **구어체 ≥ 격식체** 검색 용이 (벡터 KURE: 격식 0.733 vs 구어 1.000). 구어가 더 짧고 직접적이라 의미 매칭 쉬움.
- 이 결과가 **HyPE 무용을 정확히 예측** — 메울 어휘격차가 없는데 HyPE는 그걸 메우는 기법.
- → **"가정 말고 실측"의 가치 입증.** 논문 보고 이득(+20pp)은 도메인 전이 안 됨. 사내 규정 RAG에서도 도입 전 실측 필수.

### 사내 규정 RAG 전이 권고
1. **조항/섹션 단위 청킹 + 하이브리드(BM25+dense) + 리랭커**를 기본.
2. BM25가 강력한 베이스라인(규정은 명칭·번호·표 어휘 많음), dense는 의미질문 보완, **리랭커는 거의 항상 이득**.
3. 한국어 임베딩 = **KURE-v1**. 교차참조(규정 간 인용)는 그래프/하이브리드로 별도 보완.

---

## 4. 디렉토리 구조

```
KA-013-KFinLaw-MCP/
├── README.md                      # 프로젝트 단일 문서(개요·결과·재현)
├── scripts/
│   ├── collect_laws.py            # 법령 수집(3단계)
│   ├── download_byeolpyo.py       # 별표 PDF 전수 다운로드(멱등)
│   ├── hwp2pdf.sh                 # HWP→PDF (LibreOffice+H2Orestart)
│   └── serve_model.sh             # 정석 vLLM 서빙(venv 격리+공식 플래그+정리)
├── data/
│   ├── law_list/                  # step1(200) / final_law_list(2,596)
│   ├── raw_xml/        (gitignore) # 법령 XML 2,582개 (API 원본, 551MB)
│   ├── byeolpyo_pdf/   (gitignore) # 별표 PDF 1,083개
│   └── byeolpyo_md/    (gitignore) # 별표 마크다운(kordoc)
├── benchmark/
│   ├── corpus.py · corpus_ids.json        # 대표 코퍼스 32법령
│   ├── lawdoc.py                          # 공유 파서(조문/별표→uid)
│   ├── goldset/
│   │   ├── build_goldset.py · questions.jsonl   # 골드셋 240문
│   │   └── spotcheck.py                    # 생성기 후보 비교
│   ├── pipeline/  chunkers · embedders · retrievers
│   ├── eval/      retrieval_metrics · answer_metrics   # 레이어1 검색 · 레이어2 답변
│   ├── runner.py                          # 레이어1 검색 평가 config→리포트
│   ├── answer_runner.py                   # 레이어2 답변 생성 평가(검색→생성→채점)
│   ├── hype_index.py · hype_cache.json    # HyPE(E5)
│   ├── lightrag_index.py · lightrag_eval.py  # LightRAG(E6, 색인 보류)
│   └── reports/   (gitignore)             # 실험 결과 JSON
├── serving/
│   └── requirements.venv.lock / .full.lock  # 작동 버전 박제
└── tools/        (gitignore)              # LibreOffice+H2Orestart 로컬설치
```

---

## 5. 데이터 파이프라인

**수집 → 필터 → 전처리 → 별표**:
1. **수집** (`collect_laws.py`): 금융 키워드 28개 → 현행 200건 → 참조 재귀 → 2,596건 (XML 2,582개).
2. **금융 범위**: 키워드 1차 + 직접참조 = **931건** (재귀로 들어온 비금융 법령 제외).
3. **조문 전처리** (`lawdoc.py`): XML → 조 단위 청크. uid = `{법령ID}-{조문번호:04d}{-가지}` / 별표 `{법령ID}-별표{번호}{-가지}`.
4. **별표(부록·표)** — 검증된 결론:
   - API `type=HTML`은 JS iframe이라 직접 스크래핑 불가. 원본 HWP는 표 구조 퇴화(행이 시각적 줄위치만).
   - **PDF가 정답**(디지털·텍스트레이어). 모든 별표에 PDF·HWP·이미지 100% 동봉.
   - **kordoc(PDF 모드)**가 실용 최적(GPU 불필요, MIT). 복잡 병합셀은 MinerU 폴백.
   - 별표 1,083개 전수 다운로드(실패 0) + 변환 완료.

---

## 6. 벤치마크 설계

### 비교 축 (단계별 "무엇을 바꿔 비교하나")
| 단계 | 축(변수) | 상태 |
|---|---|---|
| A 파싱 | 별표소스(kordoc-md/평문/MinerU)·노이즈제거 | 부분 |
| B 청킹 | 조/항/고정토큰/계층(parent-doc)·브레드크럼 | ✅ E1 |
| C 임베딩 | KURE-v1/BGE-M3/KoE5·하이브리드 | ✅ E2 |
| D 검색 | vector/BM25/**하이브리드(RRF)**/LightRAG그래프 | ✅ E3, ⏸ E6 |
| E 질의/색인변환 | **HyPE**(색인측)·HyDE(질의측) | ✅ E5(HyPE) |
| F 재순위 | bge-reranker-v2-m3 | ✅ E3 |
| G 생성 | 컨텍스트포맷·인용지시 | 🟢 레이어2 |
| H 운영 | 지연·빌드시간·비용·메모리 | ✅ timing |

**원칙**: 일변수 격리(OFAT), 질문유형·register별 분해, 품질×운영비용 동시 평가.

### 골드셋 (240문, 반자동)
- **생성**: 코퍼스 조문/별표 → Mistral Small 4(`reasoning_effort=none`, 공식 채팅) Q&A → **일관성(round-trip BM25) 필터**.
- **유형 4종 균형**(각 60): factoid / crossref / byeolpyo / multihop.
- **factoid는 격식↔구어 30쌍**(공통 gold·pair_id) → HyPE 어휘격차 짝지어 측정.
- **무결성**: gold_id 300개 전부 코퍼스 존재, 멀티홉 60문 2-gold(본법+시행령).
- **방법론**(연구 근거): 검색 골드셋엔 오픈웨이트 생성기로 충분(InPars-v2 등), gold=ID라 LLM-judge 편향 무관.
  생성기·judge·답변모델 **계열 분리**로 오염 회피. 일관성 필터(Promptagator/InPars)가 핵심.

### 메트릭 (`benchmark/eval/`)
- **레이어1(검색, `retrieval_metrics.py`)** — recall@k · precision@k · MRR · nDCG@k (유형별·register별 분해). gold = 조문/별표 uid 결정론 채점.
- **레이어2(답변, `answer_metrics.py`)** — 인용정확도(자동: 인용 uid vs gold) + judge 루브릭 5종(faithfulness·correctness·relevancy·completeness·context_utilization, 1~5→0~1). 상세 §8.

---

## 7. 모델 역할 & 서빙

### 3-역할 (오염 회피)
| 역할 | 모델 | 비고 |
|---|---|---|
| 골드셋 생성기 | **Mistral Small 4** (119B) | 독립 계열, 한국어 우수(별표도 한국어 유지 — 스팟체크 근거) |
| judge | **gpt-oss-120b** | 독립, 생성기·답변모델과 다른 계열 |
| 답변모델(레이어2) | A.X-4.0 · Solar-Open · EXAONE-4.0 · Gemma 4 · Qwen3.6 | 사내 실사용(평가대상) |
> 생성·judge가 답변모델과 같으면 self-enhancement/preference leakage → 분리 필수. 전 구간 temp=0(재현성).

### 정석 서빙 환경 (재현 가능)
- **전용 venv** `/home/work/kftc_model/kfinlaw-serve` (시스템 안 건드림 — 학습 env 보호).
  - 핵심: **vllm 0.23.0, mistral_common 1.11.3** (시스템 0.20.1/1.11.2의 reasoning_effort·멀티모달 버그 회피).
  - 박제: `serving/requirements.venv.lock`. venv엔 깨진 flash_attn 없음 → 스텁 불필요.
- **격리 필수**: 셸 `PYTHONPATH`가 시스템 패키지를 오염시키므로 `env -u PYTHONPATH PYTHONNOUSERSITE=1`.
- **서빙**: `scripts/serve_model.sh {mistral|gptoss|stop}` (격리+공식 플래그+잔여워커/shm 정리 자동).
  - Mistral 공식 플래그: `--quantization fp8 --reasoning-parser mistral --tool-call-parser mistral`
    `--enable-auto-tool-choice --limit-mm-per-prompt '{"image":0}'`, 요청 시 `reasoning_effort="none"`.
- **학습 GPU 공존**: FP8 + `--gpu-memory-utilization 0.26`(가장 빡빡한 GPU 여유에 맞춤) + ctx 4096.

---

## 8. 레이어2 — 답변 생성 평가 (설계·구현)

> 레이어1(검색)이 "맞는 조문을 찾았는가"라면, 레이어2는 **답변모델이 만든 답이 정확·충실한가**.
> 골드셋·코퍼스·검색기를 **재사용**하고 답변생성+채점만 얹는다(RAGAS의 retrieval/generation 분리 구조).

### 8.1 파이프라인 (`benchmark/answer_runner.py` — 🟢 구현 완료)
질문별: **① 검색**(레이어1 최적 config = 조청킹+하이브리드+리랭커로 컨텍스트 top-k 고정) →
**② 답변 생성**(답변모델, 근거 번호 인용 지시) → **③ 채점**(judge 루브릭 + 자동 인용검증).
검색 config는 `config.yaml › answer_eval`에 고정 → 답변모델 효과만 격리. `--retrieval {good,bad,none}`로
검색품질 전이·closed-book 대조를 한 러너에서 수행. 실행 예시는 §9.

### 8.2 메트릭 (`benchmark/eval/answer_metrics.py` — 🟢 구현 완료, RAGAS 정렬)
| 메트릭 | 측정 | 채점 |
|---|---|---|
| **faithfulness(충실성)** | 답이 회수 컨텍스트에 근거(환각 없음) | judge: 답의 각 주장이 컨텍스트에 지지되는 비율 |
| **answer correctness(정확성)** | 정답(`answer`)과 일치 | **레퍼런스 기반** judge(정답+정답조문 본문 제공) |
| **answer relevancy(적합성)** | 질문에 답하는가 | judge 5점 루브릭 |
| **completeness(완결성)** | 요건/항목 누락 없는가 | judge(특히 multihop·요건 질문) |
| **citation accuracy(인용 정확도)** | 인용 조문이 `gold_ids`와 일치 | **자동**(LLM 불필요, 조문번호 파싱 vs gold) |
| **context utilization** | 회수 컨텍스트를 실제 활용 | judge |
> 인용 정확도는 자동·객관. 나머지는 gpt-oss-120b judge(레퍼런스 기반, temp=0, 답변순서 무작위화로 위치편향 완화).

#### RAGAS 대응 (정렬했으나 라이브러리 비채택)
RAGAS는 RAG 평가의 사실상 표준 프레임워크(reference-free LLM 자동채점, 검색/생성 분해). 우리 메트릭은
그 분류에 **의도적으로 정렬**하되 라이브러리는 의존성으로 쓰지 않고 직접 구현했다 — gold(정답·정답조문 uid)를
보유해 **레퍼런스 기반**으로 더 엄밀히 채점하고, judge를 답변모델과 다른 계열로 강제 분리(오염 통제)하며,
조문 uid 인용검증·한국어 프롬프트를 직접 통제(정석·재현성)하기 위함.

| 우리(`answer_metrics`) | RAGAS 대응 | 차이 |
|---|---|---|
| faithfulness | faithfulness | 동일 개념 |
| answer relevancy | answer relevancy | 동일 개념 |
| answer correctness | **answer correctness** | 둘 다 레퍼런스 필요(우리는 정답+정답조문 제공) |
| context utilization | context utilization | 동일 개념 |
| completeness | (표준 메트릭 없음, context recall에 근접) | 우리 커스텀(요건/항목 누락) |
| **citation accuracy** | (RAGAS에 없음) | 조문 uid 일치 **자동·객관**, 도메인 특화 |

> 참고: RAGAS의 context precision/recall은 *LLM 판정*이지만, 우리 레이어1(`retrieval_metrics.py`)은 조문 uid로
> **결정론적** recall@k·nDCG를 재므로 더 객관적이다. 외부 타당성 교차검증이 필요하면 골드셋 일부에 RAGAS를
> 별도 비교축으로 1회 돌려 judge 점수 상관을 확인할 수 있다(의존성·judge 모델 상이에 유의).

### 8.3 고유 비교 축
1. **답변모델 5종 비교** — 동일 검색·프롬프트에서 누가 최고 RAG 답변? (사내 모델 선정 근거 = 목적1)
2. **검색품질 → 답변품질 전이** — 좋은 검색(하이브리드+리랭커) vs 나쁜 검색(단일 BM25 top-1)이 답변에 미치는 영향.
3. **closed-book 대조** — 컨텍스트 없이(모델 지식만) vs RAG. RAG 실효·환각 누출 점검(Lewis 2021, Sufficient Context).
4. **프롬프트 변형** — 인용지시·컨텍스트 포맷·거부유도("근거 없으면 모른다").
- 유형별(factoid/crossref/byeolpyo/multihop)·register별(격식/구어) 분해.

### 8.4 엄밀성·검증
- **judge 독립성**: 답변모델과 다른 계열(gpt-oss). 같으면 자기우대(+10~25%). 결과는 **답변모델별 분리 보고**.
- **레퍼런스 기반 채점**: judge에 정답+정답조문 제공 → 자기지식 의존↓·일관성↑.
- **인간(법률가) 표본 검수** ~150문, 일치계수(κ) 보고 — ARES/KBL 관행.
- **보류 유형**(추후): 시행일자 버전 검색(연혁 데이터 필요), no-answer(임계값·기권 메트릭 필요) — 목적2 MCP 견고성과 함께.

### 8.5 산출물·연결
- `answer_runner.py` + `answer_metrics.py` → `reports/answer_{config}.json` → 답변모델×메트릭 leaderboard.
- **진행 시점**: E6까지 검색 최적 config 확정 후 착수(검색이 흔들리면 검색·생성 효과 분리 불가).
- **목적 연결**: 최고 답변모델 = 사내 배포 후보(목적1) → 목적2 MCP/CLI가 이 구성을 서빙.

---

## 9. 재현 방법

```bash
# 데이터 (대용량은 스크립트로 재생성)
export LAW_OC=<본인_인증키>                    # 국가법령정보센터 OC (§10에서 발급)
python scripts/collect_laws.py
python scripts/download_byeolpyo.py --kinds 별표

# 벤치마크
python benchmark/corpus.py                    # 코퍼스 32법령
#  (vLLM 기동) scripts/serve_model.sh mistral
python benchmark/goldset/build_goldset.py --model mistralai/Mistral-Small-4-119B-2603 \
    --reasoning-effort none --no-judge        # 골드셋 240문(일관성 필터)

# 1차 검색 실험
python benchmark/runner.py --chunker article --retriever hybrid --rerank \
    --embedder kure-v1 --byeolpyo md          # 최적 구성(recall@5 0.860)
python benchmark/runner.py --chunker article --hype --embedder kure-v1 --byeolpyo md  # E5 HyPE

# E6 LightRAG (학습 GPU 종료 후)
python benchmark/lightrag_index.py            # 전체 색인 ~20-40분
python benchmark/lightrag_eval.py --modes naive local global hybrid mix

# 레이어2 답변 생성 평가 (답변모델 서빙 + 독립 judge 후)
python benchmark/answer_runner.py --answer-model LGAI-EXAONE/EXAONE-4.0-32B \
    --judge-base-url http://localhost:8001/v1 --judge-model openai/gpt-oss-120b
python benchmark/answer_runner.py --answer-model ... --retrieval none   # closed-book 대조
```

**환경 재현**: `serving/requirements.venv.full.lock` (vllm 0.23.0 등). 임베딩은 sentence-transformers 5.5.1 + KURE-v1.

---

## 10. 데이터 소스 · 인증키
- 국가법령정보센터 Open API: https://open.law.go.kr
- 검색 `lawSearch.do` / 본문 `lawService.do` / 별표서식 `target=licbyl`
- **인증키(OC)는 사용자별로 직접 발급·설정** (코드에 하드코딩하지 않음):
  1. https://open.law.go.kr 회원가입 → OPEN API 신청 → 본인 OC 인증키 발급
  2. `export LAW_OC=<본인_인증키>` 후 `collect_laws.py` 실행 (미설정 시 안내 에러)
