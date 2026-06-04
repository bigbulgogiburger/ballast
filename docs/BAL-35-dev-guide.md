# BAL-35 — launchd 무인 스케줄링 (dev-guide)

> macOS SoT = **launchd** (`StartCalendarInterval`). cron = fallback.
> 월~금 08:00 수집(`run_collect.py`) → 08:30 브리핑(`run_briefing.py`). 스크립트는 BAL-34 산출물(참조만).

## 산출물

| 파일 | 역할 |
|---|---|
| `ops/com.ballast.collect.plist` | LaunchAgent — 월~금 08:00 수집 |
| `ops/com.ballast.briefing.plist` | LaunchAgent — 월~금 08:30 브리핑 |
| `ops/install.sh` | `__REPO_DIR__` 치환 → `~/Library/LaunchAgents/` 설치 + `launchctl load` |
| `tests/test_plist.py` | `plutil -lint`(darwin) + plistlib 구조 검증 |

## plist 설계

- `StartCalendarInterval`: Weekday 1~5 각각 dict 1개(총 5개). collect=Hour 8/Min 0, briefing=Hour 8/Min 30.
- `ProgramArguments`: `[__REPO_DIR__/.venv/bin/python, __REPO_DIR__/scripts/run_{collect,briefing}.py]`.
- `WorkingDirectory`: `__REPO_DIR__` (스크립트의 `data/ballast.db` 등 상대경로 기준).
- `StandardOutPath`/`StandardErrorPath`: `__REPO_DIR__/logs/{collect,briefing}.{out,err}.log` (`logs/`는 `.gitignore`).
- `RunAtLoad=false`: 설치 시점에 즉시 실행하지 않음(정시에만).
- `WakeForNetworkAccess=true`: 기상 직후 네트워크 가용 보장(무료 소스 호출 대비).

`__REPO_DIR__`는 플레이스홀더 — 레포에 절대경로를 커밋하지 않기 위함. `install.sh`가 설치 시 치환.

## 설치 / 해제

```bash
# 설치 (REPO_DIR 자동탐지 → 치환 → load)
bash ops/install.sh

# 상태 확인
launchctl list | grep com.ballast

# 즉시 수동 실행(테스트)
launchctl start com.ballast.collect

# 해제
launchctl unload ~/Library/LaunchAgents/com.ballast.collect.plist
launchctl unload ~/Library/LaunchAgents/com.ballast.briefing.plist
rm ~/Library/LaunchAgents/com.ballast.{collect,briefing}.plist
```

## 절전(sleep) 대응

`WakeForNetworkAccess=true`만으로는 **잠자기 상태에서 정시 기상이 보장되지 않는다**. launchd는
맥이 자고 있던 동안 놓친 `StartCalendarInterval`을 깨어날 때 한 번 따라 실행하긴 하지만, 정시 실행을
원하면 `pmset`으로 기상 스케줄을 별도 등록한다:

```bash
# 월~금 07:55 에 기상(또는 전원 켜기) — 8:00 수집 전에 깨워둠
sudo pmset repeat wakeorpoweron MTWRF 07:55:00

# 현재 예약 확인
pmset -g sched
```

### 한계

- `pmset repeat`는 **재부팅 시 초기화**될 수 있다. 부팅 후 `pmset -g sched`로 확인하고 필요 시 재등록.
- 뚜껑을 닫은(클램셸) 노트북은 외부 전원·디스플레이 없으면 기상하지 않을 수 있다.
- 완전 종료(전원 off) 상태는 `poweron` 옵션이 있어도 하드웨어/펌웨어 의존이라 비보장.
- 두 잡이 독립 실행이라, 수집이 늦어져도 브리핑은 `collect_complete_today` 선검사(04-backend §10.2)로 보류 처리되어 안전.

## cron fallback

launchd가 부적합한 환경(헤드리스 리눅스 등)에서는 cron 2행으로 대체:

```cron
0  8 * * 1-5 cd /ABSOLUTE/PATH/investbrief && .venv/bin/python scripts/run_collect.py
30 8 * * 1-5 cd /ABSOLUTE/PATH/investbrief && .venv/bin/python scripts/run_briefing.py
```

> cron은 절전/기상을 관리하지 않으므로 상시 가동 호스트에서만 신뢰. macOS 데스크톱/노트북 SoT는 launchd.
