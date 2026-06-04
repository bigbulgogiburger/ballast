#!/usr/bin/env bash
#
# Ballast launchd 설치 스크립트 (BAL-35)
#
# 동작:
#   1. REPO_DIR 자동탐지 (이 스크립트의 부모 디렉토리 = 레포 루트).
#   2. ops/*.plist 의 __REPO_DIR__ 플레이스홀더를 실제 절대경로로 치환.
#   3. ~/Library/LaunchAgents/ 에 설치하고 launchctl load 한다.
#   4. logs/ 디렉토리를 보장한다 (plist 의 Standard{Out,Error}Path 대상).
#
# 사전 준비:
#   - .venv 가 레포 루트에 존재해야 한다 (plist 가 __REPO_DIR__/.venv/bin/python 참조).
#   - scripts/run_collect.py · run_briefing.py 는 BAL-34 산출물 (참조만).
#
# 절전(sleep) 대응 (자세한 내용은 docs/BAL-35-dev-guide.md):
#   WakeForNetworkAccess=true 만으로는 잠자기 상태에서 정시 기상이 보장되지 않는다.
#   맥이 8:00 / 8:30 에 깨어 있도록 pmset wake 스케줄을 별도 등록 권장:
#     sudo pmset repeat wakeorpoweron MTWRF 07:55:00
#   (재부팅 시 pmset repeat 가 초기화될 수 있으니 dev-guide 의 한계 항목 참고.)
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LA_DIR="${HOME}/Library/LaunchAgents"
PLISTS=("com.ballast.collect.plist" "com.ballast.briefing.plist")

mkdir -p "${LA_DIR}"
mkdir -p "${REPO_DIR}/logs"

for plist in "${PLISTS[@]}"; do
	src="${REPO_DIR}/ops/${plist}"
	dst="${LA_DIR}/${plist}"
	label="${plist%.plist}"

	# 이미 로드되어 있으면 먼저 unload (재설치 멱등성).
	if launchctl list | grep -q "${label}"; then
		launchctl unload "${dst}" 2>/dev/null || true
	fi

	# __REPO_DIR__ 치환 후 설치.
	sed "s|__REPO_DIR__|${REPO_DIR}|g" "${src}" > "${dst}"

	launchctl load "${dst}"
	echo "installed: ${dst}"
done

echo "done. REPO_DIR=${REPO_DIR}"
echo "확인: launchctl list | grep com.ballast"
