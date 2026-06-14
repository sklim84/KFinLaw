"""벤치마크 공유 유틸·상수. 주요 설정은 config.yaml(단일 출처)에서 로드."""
import json
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
