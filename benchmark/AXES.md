# RAG 최적화 비교 축 (Comparison Axes)

> 목적1(사내 규정 RAG 최적화 기법 시범)의 실험 설계 기준. 금융 법령을 테스트베드로
> 각 축을 **하나씩 격리**해 정량 비교하고, 결과를 사내 규정 RAG로 전이한다.
> 하니스: `benchmark/runner.py` (config = 파서·청커·임베더·검색기·… 1조합).
> 이 문서는 **레이어1(검색 평가)** 축. **레이어2(답변 생성 평가)**는 [ANSWER_EVAL.md](ANSWER_EVAL.md) 참조.

## 설계 원칙
1. **일변수 격리(OFAT)** — 기준 config를 고정하고 축을 하나씩 스윕. 효과 분리가 명확해짐.
2. **질문 유형별 분해** — 축마다 어느 유형(factoid/crossref/byeolpyo/multihop)에 효과가 큰지 본다.
3. **품질 × 운영비용 동시 평가** — recall/nDCG와 함께 지연·인덱스시간·비용을 항상 기록.
   사내 배포에선 recall 2%p보다 지연·비용이 결정적일 수 있음.
4. **2차 상호작용은 선별적** — 전 조합(폭발) 대신 1차 스윕에서 유망한 축만 2-way로.

## 축 목록

| # | 단계 | 비교 축(변수) | 주 영향 메트릭/유형 | 전이성 | 하니스 |
|---|---|---|---|---|---|
| **A** | 파싱/전처리 | 별표 소스: kordoc-md / 별표내용 평문 / MinerU · 노이즈제거(개정이력·삭제조문) | byeolpyo, 답변정확 | ★★★ | 부분(md/plain) |
| **B** | 청킹 | 단위: 조/항/고정토큰/계층(parent-doc) · 크기·overlap · 브레드크럼 on/off | recall 전반, multihop | ★★★ | ✅ |
| **C** | 임베딩 모델 | KURE-v1 / BGE-M3 / KoE5 / ko-sroberta · dense vs 하이브리드 · 프리픽스 | recall, nDCG | ★★★ | ✅ |
| **D** | 검색 방식 | vector / BM25 / 하이브리드(RRF) / LightRAG 그래프(local·global·hybrid·mix) · top_k | crossref·multihop | ★★☆ | 부분(vector/bm25) |
| **E** | 질의/색인 변환 | **HyPE**(색인측 가설질문) · **HyDE**(질의측 가설답변) · 쿼리확장·분해 | 어휘격차, multihop | ★★★ | 신규 |
| **F** | 재순위 | 없음 / bge-reranker-v2-m3 · rerank top_n | precision, MRR | ★★★ | 신규 |
| **G** | 생성 | 컨텍스트 포맷·인용지시 · parent 확장·dedup·순서 · temp(=0 고정) | 답변 충실/정확 | ★★☆ | 신규 |
| **H** | 운영(횡단) | 인덱스 빌드시간 · 질의 지연(p50/p95) · 토큰·비용 · 메모리 | 선택 기준 | ★★★ | ✅(timing) |

## 축 E 상세 — HyPE / HyDE (어휘·문체 격차 해소)

법률 RAG의 핵심 난점: **조문은 격식 법률문어**("…하여서는 아니 된다"), **사용자는 구어 질문**
("예금 압류되면 어떻게 되나요?"). 임베딩이 이 격차를 못 넘으면 검색이 실패한다.

**파이프라인 위치(반대편):**
- **HyPE = 색인측(index-side)** — 청킹(B)과 임베딩(C) *사이*. "무엇을 임베딩할지"를 색인 시점에 변환.
- **HyDE = 질의측(query-side)** — 검색(D) *직전*. "질의를 어떻게 표현할지"를 질의 시점에 변환.
- 둘 다 "표현 변환(representation transformation)"이지만, 비용·결정성이 정반대(색인 1회 vs 질의 매번).

**논문·인용 정보(관측 2026-06-13):**
| | 출간처 | 인용(GScholar / S2) | 성숙도 |
|---|---|---|---|
| HyDE | "Precise Zero-Shot Dense Retrieval without Relevance Labels", Gao et al., **ACL 2023** 본회의 Long Papers(pp.1762–1777), arXiv 2212.10496 | **948 / 720** | 확립·널리 검증 |
| HyPE | "Bridging the Question–Answer Gap in RAG: Hypothetical Prompt Embeddings", Vake et al., **IEEE Access** Vol.13(pp.129952–129961), 2025.07 | **14 / 5** | 신생(독립 재현 부족) |
> HyPE는 인용이 적은 신생 기법이나 메커니즘이 단순·견고하고 LangChain `MultiVectorRetriever`의
> "hypothetical questions" 등 동일 패턴이 이름 이전부터 실전 사용됨. 인용 수가 적은 만큼 **우리 골드셋으로
> 직접 검증하는 가치가 큼**(목적1의 기법 검증에 부합).

- **HyPE (Hypothetical Prompt Embeddings, 2025)** — *색인 시점*에 각 청크가 답할 수 있는
  가설 질문 N개(~5)를 LLM으로 생성·임베딩해 청크로 역매핑. 검색은 **질문↔질문** 매칭.
  - 질의 시점 추가비용 0(결정론적), 비용은 색인 1회로 이전. naive 대비 논문 보고 정밀도 ~+20pp, 재현율 ~+16pp.
  - **우리에 유리**: H100×8 + 로컬 vLLM이라 ~3,600조문 × ~5질문 = 약 18k 생성은 1회 배치로 저렴.
    HyDE의 질의마다 LLM 호출(지연·비결정성)을 피함 → 법률 시스템의 재현성/감사성에 적합.
  - **주의**: 별표(표)는 산문 가정이라 가설질문 품질이 낮을 수 있음 → 표 인지 프롬프트 또는 별표는 원문/구조 검색 유지.
    가설질문이 못 덮는 질의 누락 위험 → 원문 벡터 병행(하이브리드 색인)으로 완화.
- **HyDE (2022)** — *질의 시점*에 가설 답변을 생성해 그 벡터로 검색. 질의마다 LLM 호출(지연·비용·비결정).
- **벤치마크 슬롯**: "**임베딩 대상**" 축으로 — 원문 청크(기준) vs HyPE 가설질문(N) vs (HyDE 질의측) vs 원문+질문 병행.
  임베딩모델·청커·검색기·k·리랭커 고정, 임베딩 대상만 변경. 하위축으로 **N(청크당 질문 수)** 스윕.

## 우선순위 (1차 → 2차)
- **1차 (저비용·고전이, LightRAG 인덱싱 불필요)**: **B 청킹**, **C 임베딩**, **F 리랭커**, **A 별표소스**,
  **E-HyPE**(로컬 vLLM 1회 생성) — vector/BM25 + sentence-transformers로 실행.
- **2차 (LightRAG 인덱싱 필요)**: **D 검색**(그래프 vs vector vs 하이브리드), **E-HyDE/쿼리분해**.
- **상시**: **H 운영** 기록, **G 생성**은 답변품질 평가(E3)에서.

## 1차 실험 매트릭스 (예시)
| 실험 | 고정 | 변수 |
|---|---|---|
| E1 청킹 | 임베딩=KURE-v1, 검색=vector | 조/항/고정/계층 |
| E2 임베딩 | 청킹=조, 검색=vector | KURE-v1/BGE-M3/KoE5 |
| E3 검색 | 청킹=조, 임베딩=KURE-v1 | vector/bm25/하이브리드(+리랭커) |
| E4 별표소스 | 청킹=조+별표, 임베딩=KURE-v1 | kordoc-md/평문/MinerU |
| E5 HyPE | 청킹=조, 임베딩=KURE-v1, 검색=vector | 원문 vs HyPE(N=5) vs 원문+질문 |

> **E5 측정법**: 골드셋 factoid는 같은 조문에서 **격식체+구어체 쌍**(공통 gold, `pair_id`)으로 생성된다.
> 러너가 `by_register`(formal/colloquial)로 recall을 분해하므로, "원문 임베딩에선 구어체 recall이 격식체보다
> 낮고(어휘격차), HyPE에선 그 격차가 줄어드는가"를 짝지어(paired) 직접 측정할 수 있다.

## 메트릭 (`benchmark/eval/`)
- 검색: recall@k, precision@k, MRR, nDCG@k (유형별 분해)
- 답변: LLM-judge(정확성/충실성/완결성) — 생성 LLM 고정, temp=0
- 운영: 인덱스 빌드시간, 질의 지연(p50/p95), 토큰/비용, 메모리
