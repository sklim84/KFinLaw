"""호환 shim — `python3 tool/cli.py <명령>`로 직접 실행하기 위한 진입점.

정식 진입점은 콘솔 스크립트 `kfinlaw`(pip install ./tool 후) 또는 `python -m kfinlaw_mcp.cli`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # kfinlaw_mcp 패키지 경로
from kfinlaw_mcp.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
