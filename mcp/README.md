# KFinLaw MCP (목적2)

국가법령정보센터 `law.go.kr` 라이브 API를 Claude(MCP)에 연결하는 경량 서버.
무거운 인덱싱 없이 검색·조문·별표·인용검증을 실시간 조회한다(설계·근거는 [루트 README §3](../README.md#3-kfinlaw-with-mcp)).

표준 라이브러리(`urllib`·`xml.etree`)만으로 동작하며, 외부 의존은 MCP SDK 하나다.

## 설치

```bash
uvx --from ./mcp kfinlaw-mcp          # ① 무설치 실행(uv) — 의존성 자동 해결
pip install ./mcp                     # ② 설치 → 콘솔 스크립트 kfinlaw-mcp
pip install -r mcp/requirements.txt   # ③ SDK만(직접 실행 python3 mcp/server.py 용)

export LAW_OC=<본인_인증키>             # 공통: open.law.go.kr 에서 발급
```

## Claude 연동

**A. 이 저장소에서 Claude Code (권장)** — 루트 [`.mcp.json`](../.mcp.json)에 `kfinlaw`가 이미 등록돼 있다(`${LAW_OC}` 환경변수 확장이라 키는 커밋되지 않음). `LAW_OC`를 환경에 둔 채 저장소에서 Claude Code를 열면 승인 프롬프트가 뜨고, 승인하면 9개 도구가 붙는다.

```bash
claude mcp list        # → kfinlaw: python3 mcp/server.py - ✔ Connected
```

**B. 다른 경로·사용자 스코프** —

```bash
claude mcp add kfinlaw --env LAW_OC=<본인_인증키> -- python3 /절대경로/mcp/server.py
```

**C. Claude Desktop** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kfinlaw": {
      "command": "python3",
      "args": ["/절대경로/mcp/server.py"],
      "env": { "LAW_OC": "<본인_인증키>" }
    }
  }
}
```

**D. Claude Code 플러그인** — 마켓플레이스로 원클릭 설치(설치 시 OC키 입력):

```bash
/plugin marketplace add sklim84/KFinLaw
/plugin install kfinlaw-mcp@kfinlaw
```

직접 실행(디버그): `LAW_OC=<키> python3 mcp/server.py` (stdio 대기).

## 배포

- **uvx(무설치):** `uvx --from <경로|git+URL> kfinlaw-mcp` — uv가 의존성까지 빌드·실행.
- **PyPI(유지보수자):** `cd mcp && uv build && uv publish`(또는 `python -m build && twine upload dist/*`). 공개 후엔 어디서나 `uvx kfinlaw-mcp`.
- **플러그인:** 저장소에 [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) + [`mcp/.claude-plugin/plugin.json`](.claude-plugin/plugin.json) 동봉(MCP 서버는 `uvx --from ${CLAUDE_PLUGIN_ROOT} kfinlaw-mcp`로 기동).

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
