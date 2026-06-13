#!/usr/bin/env bash
# HWP → PDF 변환 래퍼 (루트 없이 로컬 설치한 LibreOffice + H2Orestart 사용)
# 사용법:
#   scripts/hwp2pdf.sh <입력.hwp> [출력디렉토리]
#   scripts/hwp2pdf.sh "data/byeolpyo_hwp/*.hwp" out/pdf     # 다중 변환
#
# 의존:
#   - LibreOffice 26.2.4 (tools/lo_root, dpkg-deb -x 로컬 추출)
#   - H2Orestart 0.7.12 (tools/lo_home 사용자 프로파일에 등록, HWP 읽기 필터)
#   - Java 11 (시스템 /usr/bin/java)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOFFICE="$ROOT/tools/lo_root/opt/libreoffice26.2/program/soffice"
# H2Orestart 확장이 등록된 사용자 프로파일을 HOME으로 지정해야 HWP 필터가 로드됨
export HOME="$ROOT/tools/lo_home"

if [[ ! -x "$SOFFICE" ]]; then
  echo "ERROR: LibreOffice가 없습니다 ($SOFFICE). tools/ 설치를 확인하세요." >&2
  exit 1
fi

OUTDIR="${2:-$ROOT/out/hwp2pdf}"
mkdir -p "$OUTDIR"

# 주의: H2Orestart(HWP 필터)는 lo_home 프로파일에 등록돼 있으므로 HOME을 바꾸거나
# UserInstallation을 분리하면 안 됨(필터 미로드 → "source file could not be loaded").
"$SOFFICE" --headless --convert-to pdf --outdir "$OUTDIR" "$1"
echo "완료 → $OUTDIR"
