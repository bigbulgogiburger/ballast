"""BAL-35 launchd plist 검증.

- plutil -lint: macOS(darwin) 한정 (plutil 없음 → skip).
- plistlib 파싱: 플랫폼 무관 (StartCalendarInterval·WakeForNetworkAccess 등 구조 검증).
"""
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

_OPS_DIR = Path(__file__).resolve().parent.parent / "ops"
COLLECT_PLIST = _OPS_DIR / "com.ballast.collect.plist"
BRIEFING_PLIST = _OPS_DIR / "com.ballast.briefing.plist"


def _load(path: Path) -> dict:
    with path.open("rb") as fp:
        return plistlib.load(fp)


@pytest.mark.skipif(sys.platform != "darwin", reason="plutil은 macOS 전용")
@pytest.mark.parametrize("plist", [COLLECT_PLIST, BRIEFING_PLIST])
def test_plutil_lint(plist: Path) -> None:
    result = subprocess.run(
        ["plutil", "-lint", str(plist)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("plist", [COLLECT_PLIST, BRIEFING_PLIST])
def test_weekday_coverage_mon_to_fri(plist: Path) -> None:
    data = _load(plist)
    intervals = data["StartCalendarInterval"]
    weekdays = {entry["Weekday"] for entry in intervals}
    assert weekdays == {1, 2, 3, 4, 5}


def test_collect_schedule_hour8_min0() -> None:
    intervals = _load(COLLECT_PLIST)["StartCalendarInterval"]
    assert all(e["Hour"] == 8 and e["Minute"] == 0 for e in intervals)


def test_briefing_schedule_hour8_min30() -> None:
    intervals = _load(BRIEFING_PLIST)["StartCalendarInterval"]
    assert all(e["Hour"] == 8 and e["Minute"] == 30 for e in intervals)


@pytest.mark.parametrize("plist", [COLLECT_PLIST, BRIEFING_PLIST])
def test_wake_for_network_access(plist: Path) -> None:
    assert _load(plist)["WakeForNetworkAccess"] is True


@pytest.mark.parametrize(
    ("plist", "script"),
    [
        (COLLECT_PLIST, "scripts/run_collect.py"),
        (BRIEFING_PLIST, "scripts/run_briefing.py"),
    ],
)
def test_program_arguments_reference_script(plist: Path, script: str) -> None:
    args = _load(plist)["ProgramArguments"]
    assert args[0].endswith(".venv/bin/python")
    assert args[1].endswith(script)


@pytest.mark.parametrize("plist", [COLLECT_PLIST, BRIEFING_PLIST])
def test_run_at_load_false(plist: Path) -> None:
    assert _load(plist)["RunAtLoad"] is False
