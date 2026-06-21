# KFinLaw MCP (목적2)

국가법령정보센터 `law.go.kr` 라이브 API를 Claude(MCP)에 연결하는 경량 서버.
무거운 인덱싱 없이 검색·조문·별표·인용검증을 실시간 조회한다(설계·근거는 [루트 README §3](../README.md#3-kfinlaw-with-mcp)).

표준 라이브러리(`urllib`·`xml.etree`)만으로 동작하며, 외부 의존은 MCP SDK 하나다.

## 설치 · 실행

```bash
pip install -r mcp/requirements.txt          # mcp SDK
export LAW_OC=<본인_인증키>                    # open.law.go.kr 에서 발급
python mcp/server.py                          # stdio MCP 서버
```

Claude Code에 등록:

```bash
claude mcp add kfinlaw --env LAW_OC=<본인_인증키> -- python /절대경로/mcp/server.py
```

또는 설정 JSON에 직접:

```json
{
  "mcpServers": {
    "kfinlaw": {
      "command": "python",
      "args": ["/절대경로/mcp/server.py"],
      "env": { "LAW_OC": "<본인_인증키>" }
    }
  }
}
```

## 도구 (9종)

| 도구 | 기능 | API target |
|---|---|---|
| `search_law` | 법령명·키워드 검색(금융 코퍼스 우선 정렬) | law |
| `get_article` | 법령명+조번호 → 조문 본문(`effective_date`로 시행일 버전) | law / eflaw |
| `list_law_versions` | 시행일 버전 목록(개정 이력) | eflaw |
| `get_byeolpyo` | 별표·서식 검색(요율·비율·한도·서식) | licbyl |
| `search_admrul` | 행정규칙 검색 — 금융위 감독규정·금감원 시행세칙 | admrul |
| `get_admrul` | 행정규칙 본문 조회(`article_no`로 특정 조) | admrul |
| `get_term` | 법령용어 법적 정의 | lstrm |
| `trace_delegation` | 조문의 위임(대통령령·고시) 탐지 → 시행령·감독규정 후보 | law / admrul |
| `verify_citation` | 「법령명」 제N조 인용의 실재 검증(환각 차단) | law |

## 금융 특화

- **감독규정(`search_admrul`/`get_admrul`)** — 금융 실무 규범은 법·시행령이 아니라 금융위 고시(감독규정)에 있는 경우가 많다.
- **위임 체인 추적(`trace_delegation`)** — 법 → 시행령 → 감독규정으로 이어지는 위임을 따라가 실제 기준을 찾는다.
- **금융 코퍼스 스코핑** — `search_law`가 핵심 32개 금융법(`rag/benchmark/corpus_ids.json`)을 위로 정렬한다.
- **법령용어(`get_term`)** — 금융 정의어(부보금융회사 등)의 법적 뜻풀이.
