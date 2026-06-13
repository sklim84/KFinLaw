# KA-013-KFinLaw-MCP

금융결제원(KFTC) 연구 과제 — 금융 법령을 테스트베드로 한 **RAG 최적화 기법 시범**과 **국가법령정보센터 연계 MCP/CLI** 구축.

---

## 🎯 프로젝트 목적 (두 가지)

### 1. 사내 규정 RAG 파이프라인 최적화 기법 시범 테스트
- 금융 법령 코퍼스는 **테스트베드(proving ground)**. 최종 적용 대상은 **사내 규정 RAG**.
- 핵심 산출물은 "작동하는 시스템"이 아니라 **전이 가능한 최적화 기법의 정량 검증·문서화**
  (청킹 전략, 임베딩 선정, 그래프 RAG, HWP/PDF/별표 파서 선택 등).
- 사내 규정도 HWP/PDF/docx 문서이므로 별표·HWP 파싱·청킹 실험이 그대로 전이됨.
- **방향: 기법별 비교 실험 우선.** 전수 인덱싱 불필요, 대표 샘플로 충분.

### 2. 국가법령정보센터 연계 MCP/CLI 구축 (Claude 등 호환)
- 국가법령정보센터 Open API(`law.go.kr`, OC: `captiong84`)와 연계된 **MCP 서버 + CLI**.
- **방향: 라이브 API 연계 중심.** 검색/조문 조회/별표/인용 검증을 그대로 도구화. 무거운 RAG 없이 경량·신선도 우선.

> 두 목적은 상호보완 — 법령으로 기법을 검증(목적1)하고 그 결과를 법령 MCP/CLI로 제품화(목적2).
> **작업 순서: 벤치마크 하니스 먼저 → 그다음 MCP/CLI.**

---

## 📊 진행 현황

| 단계 | 상태 | 결과 |
|---|---|---|
| 법령 수집 (Open API) | ✅ 완료 | 2,596건 목록 / 본문 XML 2,582개 (재귀 참조로 비금융 법령 다수 혼입) |
| 금융 범위 확정 | ✅ 분석 | 키워드 1차(200) + 직접참조 = **931건** (코드화 예정) |
| 별표 파서 비교 | ✅ 완료 | API HTML 불가 → PDF 경로 채택. kordoc(PDF) 최적, MinerU는 스캔용 폴백 |
| 별표 PDF 전수 다운로드 | ✅ 완료 | 1,083/1,083 (실패 0), 98.8MB |
| 별표 kordoc 일괄 변환 | ✅ 완료 | 1,083/1,083 (62초). 격자표 69% / 비표형 목록 31% |
| **벤치마크 하니스** | 🔜 진행 | 골드셋·파이프라인·메트릭·리포트 (목적1 핵심 인프라) |
| MCP/CLI (라이브 API) | ⬜ 대기 | 하니스 완료 후 착수 |

---

## 🛠 기술 방향

- **RAG**: LightRAG (그래프 기반, `lightrag-hku`) — 벡터+그래프 하이브리드, 상위법↔하위법·참조조문을 그래프로
- **임베딩**: KURE-v1 (BGE-M3 한국어 파인튜닝, 검색 SOTA) / 비교군 BGE-M3·KoE5
- **LLM**: 로컬 vLLM (H100 80GB × 8), OpenAI 호환 엔드포인트
- **별표 파서**: PDF 첨부 + kordoc(PDF 모드). 복잡 병합셀은 MinerU 폴백
- **조문 청킹**: 조(條) 단위 + 브레드크럼(법령명 > 장/절 > 조) + 교차참조 그래프 엣지

---

## 📁 디렉토리 구조

```
KA-013-KFinLaw-MCP/
├── README.md                  # 이 문서
├── scripts/
│   ├── collect_laws.py        # 법령 수집 (3단계)
│   ├── download_byeolpyo.py   # 별표 PDF 전수 다운로드 (멱등·재시도)
│   └── hwp2pdf.sh             # HWP→PDF 변환 (LibreOffice+H2Orestart)
├── data/
│   ├── law_list/             # step1_keyword_laws(200) / final_law_list(2,596)
│   ├── raw_xml/              # 법령 본문 XML 2,582개 (API 원본, 551MB)
│   ├── byeolpyo_pdf/         # 별표 PDF 1,083개 (94MB)
│   └── byeolpyo_md/          # 별표 마크다운 1,083개 (kordoc 변환)
├── benchmark/                # (예정) RAG 기법 비교 하니스
│   ├── corpus.py · corpus_ids.json
│   ├── goldset/             # 반자동 LLM 생성 Q&A + 정답 조문
│   ├── pipeline/            # 파서·청커·임베더·검색기 (플러그인)
│   ├── eval/                # 검색·답변·운영 메트릭
│   └── runner.py · reports/
├── tools/                    # 루트 없이 로컬 설치
│   ├── lo_root/ · lo_home/  # LibreOffice 26.2 + H2Orestart (HWP→PDF)
│   └── H2Orestart.oxt
└── tests/byeolpyo_parser/   # 파서 비교 테스트 산출물
```

---

## 🔑 핵심 발견 (별표 처리)

- **별표는 PDF가 정답**: API `type=HTML`은 JS iframe이라 직접 스크래핑 불가. 원본 HWP는 표가 "1행×N열, 셀 안 줄바꿈"으로
  퇴화돼 행 복원 불가. **PDF는 디지털(텍스트 레이어)** 이라 좌표 기반 표 재구성 가능.
- 모든 별표에 **PDF·HWP·이미지 100% 동봉**.
- **kordoc(PDF)** 가 실용 최적 — GPU 불필요, 분당 ~1,000건, MIT 라이선스.

---

## 📌 데이터 소스 / 인증

- 국가법령정보센터 Open API: https://open.law.go.kr — OC 인증키 `captiong84`
- 검색: `lawSearch.do` / 본문: `lawService.do` / 별표서식: `target=licbyl`
