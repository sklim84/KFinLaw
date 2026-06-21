# KFinLaw

**한국 금융 법령으로 한국어 RAG 검색 기법을 정량 비교·평가**하고, 그 결과로
**국가법령정보센터 연계 MCP/CLI를 구현**한다.

`최종 업데이트 2026-06-21`

[**빠른 시작**](#빠른-시작) · [핵심 결과](#핵심-결과) · [구성](#구성) · [벤치마크 상세](rag/README.md) · [도구 사용법](tool/README.md)

---

## 빠른 시작

`law.go.kr` 라이브 API로 한국 금융 법령을 조회하는 **MCP 서버 + CLI**. 인증키(OC)는 [open.law.go.kr](https://open.law.go.kr)에서 발급한다.

```bash
export LAW_OC=<본인_인증키>

# CLI: 무설치 실행(uv)
uvx --from ./tool kfinlaw article 은행법 제1조
uvx --from ./tool kfinlaw search 전자금융 --json

# Claude Code 플러그인: 마켓플레이스 등록 후 설치
/plugin marketplace add sklim84/KFinLaw
/plugin install kfinlaw-mcp@kfinlaw
```

설치·연동(MCP `.mcp.json` · Claude Desktop · PyPI)과 전체 명령(9개 도구)은 **[tool/README](tool/README.md)**.

---

## 핵심 결과

한국 금융 법령으로 RAG 검색·답변 기법을 통제 실험한 결론이다(전체 보고서는 **[rag/README](rag/README.md)**):

- ✅ **검색 최적은 하이브리드 + 리랭커**: Lexical recall@5 0.86, 리랭커 적용이 성능을 가장 크게 좌우.
- ❌ **증강(HyPE·HyDE·LightRAG)은 효과 없음**: 모두 증강 전보다 낮음, "정교 ≠ 우위".
- 🔬 **어휘격차가 크면 최적이 벡터 + 리랭커로 역전**: Semantic에서 BM25 붕괴(0.835→0.510), 벡터는 불변.
- ✅ **답변모델 품질은 크기로 예측 안 됨**: 31B gemma-4가 100B·67B를 앞섬.
- 📍 **위치 질의("○○법 제5조")는 RAG의 약점**(최고 recall 0.66) → **구조적 조회(MCP/CLI)**가 정답.

마지막 발견이 **MCP/CLI를 구현한 직접적 근거**다.

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
│   └── kfinlaw_mcp/ · pyproject.toml · .claude-plugin/
├── .mcp.json            # Claude Code MCP 등록(kfinlaw)
└── .claude-plugin/      # 플러그인 마켓플레이스
```

---

## 왜 이렇게

금융 법령 질의응답에 RAG를 도입하려면 청킹·임베딩·검색기·증강 등 설계 선택이 많지만, **한국어 법령 도메인에서 무엇이 실제로 효과적인지에 대한 정량 근거는 빈약하다.** 영어·일반 도메인의 통념(그래프 RAG·가설질의 증강이 검색을 개선한다, 큰 모델이 더 낫다)을 검증 없이 들여오면 비용만 늘고 성능은 오히려 떨어질 수 있다.

그래서 ① 한국 금융 법령을 테스트베드로 **기법별 효과를 통제 실험으로 정량 측정**하고(→ [`rag/`](rag/README.md)), ② 그 결과(특히 위치 질의 한계)에서 도출한 **MCP/CLI를 구현**했다(→ [`tool/`](tool/README.md)). 최종 적용 대상은 사내 법령·규정 검색 서비스다.
