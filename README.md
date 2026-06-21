# KFinLaw

**한국 금융 법령으로 한국어 RAG 검색 기법을 정량 비교·평가**하고, 그 결과로
**국가법령정보센터 연계 MCP/CLI를 구현**한다.

`최종 업데이트 2026-06-21`

[**Quick Start**](#quick-start) · [도구](#도구) · [핵심 결과](#핵심-결과) · [구성](#구성) · [벤치마크 상세](rag/README.md) · [도구 사용법](tool/README.md)

---

## Quick Start

`law.go.kr` 라이브 API로 한국 금융 법령을 조회하는 **MCP 서버 + CLI**. 인증키(OC)는 [open.law.go.kr](https://open.law.go.kr)에서 발급한다.

```bash
export LAW_OC=<본인_인증키>

# CLI: 무설치 실행(uv)
uvx --from ./tool kfinlaw article 은행법 제1조
uvx --from ./tool kfinlaw search 전자금융 --json

# Claude Code 플러그인: 마켓플레이스 등록 후 설치
/plugin marketplace add sklim84/KFinLaw
/plugin install kfinlaw@kfinlaw
```

설치·연동(MCP `.mcp.json` · Claude Desktop · PyPI)과 전체 명령(9개 도구)은 **[tool/README](tool/README.md)**.

---

## 도구

`law.go.kr` 라이브 API를 **MCP 도구 9종**으로 노출하고, 같은 코어를 **CLI**로도 쓴다(설치·연동은 [tool/README](tool/README.md)).

| MCP 도구 | 기능 | API |
|---|---|---|
| `search_law` | 법령명·키워드 검색(금융 코퍼스 우선) | law |
| `get_article` | 법령명+조번호 → 조문 본문(시행일 버전) | law / eflaw |
| `list_law_versions` | 시행일 버전 목록(개정 이력) | eflaw |
| `get_byeolpyo` | 별표·서식 검색(요율·비율·한도) | licbyl |
| `search_admrul` | 행정규칙 검색(금융위 감독규정·금감원 시행세칙) | admrul |
| `get_admrul` | 행정규칙 본문(특정 조) | admrul |
| `get_term` | 법령용어 법적 정의 | lstrm |
| `trace_delegation` | 위임(대통령령·고시) 탐지 → 시행령·감독규정 | law / admrul |
| `verify_citation` | 「법령명」 제N조 인용의 실재 검증(환각 차단) | law |

**CLI**: 터미널에서 `kfinlaw <명령>` (사람용 출력 / `--json` 파이프).
`search · article · versions · byeolpyo · admrul · admrul-text · term · delegation · verify`

---

## 핵심 결과

한국 금융 법령으로 RAG 검색·답변 기법을 실험한 결과다(전체 보고서는 **[rag/README](rag/README.md)**):

- ✅ **검색 최적은 하이브리드 + 리랭커**: Lexical recall@5 0.86, 리랭커 적용이 성능을 가장 크게 좌우.
- ❌ **증강(HyPE·HyDE·LightRAG)은 효과 없음**: 모두 증강 전보다 낮음, "정교 ≠ 우위".
- 🔬 **어휘격차가 크면 최적이 벡터 + 리랭커로 역전**: Semantic에서 BM25 붕괴(0.835→0.510), 벡터는 불변.
- ✅ **답변모델 품질은 크기로 예측 안 됨**: 31B gemma-4가 100B·67B를 앞섬.
- 📍 **위치 질의("○○법 제5조")는 RAG의 약점**(최고 recall 0.66) → **구조적 조회(MCP/CLI)**가 정답.

> **표 1. 종합 리더보드** (검색 구성별 Lexical·Semantic recall@5·MRR·nDCG@10, 평균 recall@5 순). 방법론·전체 분석은 [rag/README](rag/README.md).

| # | 검색기 | 리랭커 | 증강 | **Lexical**<br>R@5 | MRR | nDCG | **Semantic**<br>R@5 | MRR | nDCG | 평균<br>R@5 |
|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 🏆 | 하이브리드(BM25+KURE) | bge-reranker-v2-m3 | - | 0.860 | 0.775 | 0.793 | 0.756 | 0.661 | 0.684 | **0.808** |
| 2 | 하이브리드(BM25+KURE) | ko-reranker | - | 0.838 | 0.729 | 0.754 | 0.769 | 0.672 | 0.691 | **0.803** |
| 3 | 벡터(KURE) | bge-reranker-v2-m3 | - | 0.808 | 0.748 | 0.751 | 0.777 | 0.661 | 0.684 | **0.793** |
| 4 | 하이브리드(BM25+KURE) | ko-reranker-8k | - | 0.863 | 0.785 | 0.804 | 0.708 | 0.608 | 0.637 | **0.785** |
| 5 | 하이브리드(BM25+KURE) | bge-reranker-v2-m3 | HyDE | 0.812 | 0.743 | 0.750 | 0.742 | 0.657 | 0.669 | **0.777** |
| 6 | 벡터(KURE) | - | - | 0.767 | 0.656 | 0.672 | 0.767 | 0.612 | 0.648 | **0.767** |
| 7 | 하이브리드(BM25+KURE) | bge-reranker-large | - | 0.798 | 0.699 | 0.719 | 0.729 | 0.621 | 0.644 | **0.764** |
| 8 | LightRAG(naive) | - | - | 0.738 | 0.639 | 0.648 | 0.767 | 0.616 | 0.649 | **0.752** |
| 9 | 하이브리드(BM25+KURE) | - | - | 0.831 | 0.710 | 0.735 | 0.658 | 0.562 | 0.588 | **0.745** |
| 10 | 벡터(KURE) | bge-reranker-v2-m3 | HyDE+HyPE | 0.721 | 0.680 | 0.672 | 0.667 | 0.588 | 0.595 | **0.694** |
| 11 | BM25 | - | - | 0.835 | 0.707 | 0.741 | 0.510 | 0.397 | 0.430 | **0.673** |
| 12 | LightRAG(mix) | - | - | 0.665 | 0.606 | 0.616 | 0.665 | 0.552 | 0.572 | **0.665** |
| 13 | 벡터(KURE) | - | HyPE | 0.721 | 0.622 | 0.637 | 0.579 | 0.500 | 0.521 | **0.650** |
| 14 | 벡터(KURE) | - | HyDE | 0.652 | 0.558 | 0.572 | 0.592 | 0.469 | 0.499 | **0.622** |
| 15 | 벡터(KURE) | - | HyDE+HyPE | 0.562 | 0.515 | 0.529 | 0.490 | 0.382 | 0.416 | **0.526** |

---

## 구성

| 디렉토리 | 내용 | 문서 |
|---|---|---|
| **`rag/`** | RAG 검색·답변 **벤치마크**(연구): 코퍼스·골드셋·실험·재현 | [rag/README](rag/README.md) |
| **`tool/`** | `kfinlaw` 패키지: **MCP 서버 + CLI** (`law.go.kr` 라이브 API) | [tool/README](tool/README.md) |

```
KFinLaw/
├── rag/      # RAG 벤치마크 (cd rag 후 python -m benchmark.<모듈>)
│   └── benchmark/ · scripts/ · serving/ · config.yaml · data/ · tools/
├── tool/     # kfinlaw 패키지: MCP 서버 + CLI
│   └── kfinlaw/ · pyproject.toml · .claude-plugin/
├── .mcp.json            # Claude Code MCP 등록(kfinlaw)
└── .claude-plugin/      # 플러그인 마켓플레이스
```

---

## 왜 이렇게

금융 법령 질의응답에 RAG를 도입하려면 청킹·임베딩·검색기·증강 등 설계 선택이 많지만, **한국어 법령 도메인에서 무엇이 실제로 효과적인지에 대한 정량 근거는 빈약하다.** 영어·일반 도메인의 통념(그래프 RAG·가설질의 증강이 검색을 개선한다, 큰 모델이 더 낫다)을 검증 없이 들여오면 비용만 늘고 성능은 오히려 떨어질 수 있다.

그래서 ① 한국 금융 법령을 테스트베드로 **기법별 효과를 통제 실험으로 정량 측정**하고(→ [`rag/`](rag/README.md)), ② 그 결과(특히 위치 질의 한계)에서 도출한 **MCP/CLI를 구현**했다(→ [`tool/`](tool/README.md)). 최종 적용 대상은 사내 법령·규정 검색 서비스다.
