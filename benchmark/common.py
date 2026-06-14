"""벤치마크 공유 유틸·상수. 주요 설정은 config.yaml(단일 출처)에서 로드."""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

# ---- config.yaml (단일 설정 출처) ----
CONFIG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text(encoding="utf-8"))

# 자주 쓰는 값 단축 (코드 가독성용; 원본은 CONFIG)
CTX_CHARS = CONFIG["goldset"]["ctx_chars"]
DEFAULT_ENDPOINT = CONFIG["serving"]["endpoint"]
LIGHTRAG_MODES = CONFIG["lightrag"]["modes"]
EMBEDDER_MODELS = CONFIG["models"]["embedders"]


def txt(elem, tag):
    """XML 하위 태그 텍스트(없으면 빈 문자열, 공백 제거)."""
    v = elem.findtext(tag)
    return (v or "").strip()


def byeolpyo_key(num, ga):
    """별표 식별 키 = 별표번호 + 가지번호. 다운로드/변환 파일명·uid 공통 규칙(반드시 동기 유지)."""
    return num + (f"-{ga}" if ga and ga != "0" else "")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---- OpenAI 호환 LLM 클라이언트 (vLLM, 의존성 없음) ----
def llm_chat(base_url, model, system, user, temperature=0.0, max_tokens=1024,
             json_mode=True, reasoning_effort=None, max_retries=3):
    """단일 채팅 호출. 전 구간 temp=0(재현성).
    json_mode=True면 response_format json_object 요청(미지원 400시 자동 제거 후 폴백).
    reasoning_effort: Mistral Small 4 등 추론모델 공식 per-request 파라미터(예: 'none')."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}  # vLLM 가이드 JSON
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    def _post(pl):
        req = urllib.request.Request(url, data=json.dumps(pl).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer EMPTY"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]

    for i in range(max_retries):
        try:
            return _post(payload)
        except urllib.error.HTTPError as e:
            if e.code == 400 and "response_format" in payload:  # JSON 미지원 폴백
                payload.pop("response_format", None)
                continue
            if i < max_retries - 1:
                time.sleep(2)
            else:
                print(f"  [LLM HTTP {e.code}] {e}", file=sys.stderr)
                return None
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(2)
            else:
                print(f"  [LLM ERROR] {e}", file=sys.stderr)
                return None


def parse_json(text):
    """LLM 응답에서 첫 JSON 객체 추출(코드펜스·서두 텍스트 허용)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
