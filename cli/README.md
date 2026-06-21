# KFinLaw CLI (목적2)

§3 MCP와 **같은 `lawapi` 코어**를 쓰는 터미널용 도구. 법령 검색·조문 조회·별표·감독규정·
위임 추적·인용 검증을 셸에서 수행하고, 결과를 사람이 읽기 좋은 형식 또는 `--json`(스크립트·
파이프라인용)으로 출력한다.

CLI 구현은 패키지에 함께 들어 있어(`mcp/kfinlaw_mcp/cli.py`), **MCP 서버와 한 패키지·한 번의
배포**로 묶인다 — `pip install ./mcp` 하면 `kfinlaw`(CLI)와 `kfinlaw-mcp`(서버)가 같이 깔린다.

## 실행

```bash
export LAW_OC=<본인_인증키>                 # open.law.go.kr 에서 발급

uvx --from ./mcp kfinlaw article 은행법 제1조   # 무설치(uv)
pip install ./mcp && kfinlaw search 전자금융     # 설치 후 콘솔 스크립트
python3 cli/kfinlaw.py search 전자금융           # 미설치 직접 실행(shim)
```

## 명령

| 명령 | 기능 |
|---|---|
| `search <질의> [--all]` | 법령 검색(금융 코퍼스 우선, `--all`로 전체) |
| `article <법령> <조> [--date YYYYMMDD]` | 조문 본문(시행일 버전) |
| `versions <법령>` | 시행일 버전 목록 |
| `byeolpyo <질의>` | 별표·서식 검색 |
| `admrul <질의>` | 행정규칙(감독규정) 검색 |
| `admrul-text <ID> [--article 제N조]` | 행정규칙 본문 |
| `term <용어>` | 법령용어 정의 |
| `delegation <법령> <조>` | 위임(시행령·감독규정) 추적 |
| `verify "<문장>"` | 「법령명」 제N조 인용 실재 검증 |

공통 옵션 `--json` 으로 JSON 출력(예: `kfinlaw search 전자금융 --json | jq .`).
