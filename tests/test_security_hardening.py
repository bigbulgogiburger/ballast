"""BAL-38 보안 하드닝 회귀 — 바인딩·시크릿 미트래킹·재생성 게이트.

방어선:
- app/main.py 소스에 0.0.0.0 바인딩 리터럴이 코드로 존재하지 않음(주석 제외, AST 스캔).
- .gitignore 가 data/·.env 를 무시 (금융정보·시크릿 유출 방지).
- .env / data/ 가 git 에 미트래킹 (.env.example 템플릿만 추적).
- /api/regenerate 의 403 게이트 회귀 (외부 host 거부).
"""

import ast
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "app" / "main.py"
GITIGNORE = REPO_ROOT / ".gitignore"


def _git_ls_files(*paths: str) -> list[str]:
    """git ls-files 결과 행 리스트(추적 파일만). 미추적이면 빈 리스트."""
    out = subprocess.run(
        ["git", "ls-files", "--", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


@pytest.mark.unit
def test_main_has_no_zero_bind_literal_in_code() -> None:
    """AST 스캔: 0.0.0.0 문자열 리터럴이 코드에 없음(주석은 AST 비포함)."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert not any("0.0.0.0" in s for s in literals)


@pytest.mark.unit
def test_gitignore_ignores_data_and_env() -> None:
    """.gitignore 가 data/·.env 라인을 보유."""
    lines = {line.strip() for line in GITIGNORE.read_text(encoding="utf-8").splitlines()}
    assert "data/" in lines
    assert ".env" in lines


@pytest.mark.unit
def test_env_not_tracked() -> None:
    """.env 는 git 에 추적되지 않음."""
    assert _git_ls_files(".env") == []


@pytest.mark.unit
def test_data_dir_not_tracked() -> None:
    """data/ 하위 파일은 git 에 추적되지 않음(금융정보 유출 방지)."""
    assert _git_ls_files("data/") == []


@pytest.mark.unit
def test_env_example_tracked() -> None:
    """.env.example(키 템플릿)은 추적되어야 함."""
    assert ".env.example" in _git_ls_files(".env.example")


@pytest.mark.unit
def test_regenerate_has_403_gate() -> None:
    """AST: regenerate 함수가 HTTPException(403) 게이트를 보유(외부 host 거부 회귀)."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "regenerate"
    )
    raised = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and getattr(node.exc.func, "id", None) == "HTTPException"
    ]
    assert raised, "regenerate 에 raise HTTPException 게이트 없음"
    args = [a for r in raised for a in r.exc.args if isinstance(a, ast.Constant)]
    assert any(a.value == 403 for a in args)
