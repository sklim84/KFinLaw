"""호환 shim — `python3 mcp/server.py`로 직접 실행하기 위한 진입점.

정식 진입점은 콘솔 스크립트 `kfinlaw-mcp` 또는 `python -m kfinlaw.server`.
이 shim은 패키지 미설치 상태(저장소 동봉 .mcp.json)에서도 바로 띄우기 위한 것이다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # kfinlaw 패키지 경로
from kfinlaw.server import main  # noqa: E402

if __name__ == "__main__":
    main()
