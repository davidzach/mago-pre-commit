"""End-to-end tests against the real mago binary and a real Git commit. Skipped when mago is missing."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from mago_pre_commit.cli import main

pytestmark = pytest.mark.skipif(shutil.which("mago") is None, reason="mago is not installed")

ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

GREETER = """<?php

declare(strict_types=1);

namespace App;

final class Greeter
{
    public function greet(string $name): string
    {
        return 'Hello ' . $name;
    }
}
"""

# Uses Greeter from another file: analyze must see the whole project to resolve it.
CLEAN = """<?php

declare(strict_types=1);

namespace App;

final class Welcome
{
    public function text(): string
    {
        $greeter = new Greeter();

        return $greeter->greet('you');
    }
}
"""

TYPE_ERROR = CLEAN.replace("public function text(): string", "public function text(): int")
UNFORMATTED = CLEAN.replace("final class Welcome\n{", "final class Welcome {")
SYNTAX_ERROR = "<?php\n\nfunction (\n"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "legacy").mkdir()
    (tmp_path / "src" / "Greeter.php").write_text(GREETER, encoding="utf-8")
    (tmp_path / "mago.toml").write_text(
        '[source]\npaths = ["src", "legacy"]\nexcludes = ["legacy"]\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAGO_BINARY", raising=False)
    return tmp_path


def write(project: Path, content: str, name: str = "src/Welcome.php") -> str:
    (project / name).write_text(content, encoding="utf-8")
    return name


@pytest.mark.parametrize("command", ["lint", "analyze", "format"])
def test_clean_file_passes(project: Path, command: str) -> None:
    assert main([command, write(project, CLEAN)]) == 0


@pytest.mark.parametrize("command", ["lint", "analyze", "format"])
def test_syntax_error_fails(project: Path, command: str) -> None:
    assert main([command, write(project, SYNTAX_ERROR)]) == 1


def test_analyze_type_error_fails(project: Path) -> None:
    assert main(["analyze", write(project, TYPE_ERROR)]) == 1


def test_format_shows_diff_and_keeps_file(project: Path, capfd: pytest.CaptureFixture[str]) -> None:
    name = write(project, UNFORMATTED)
    assert main(["format", name]) == 1
    assert "+++ modified" in capfd.readouterr().out
    assert (project / name).read_text(encoding="utf-8") == UNFORMATTED


def test_format_write_fixes_file(project: Path) -> None:
    name = write(project, UNFORMATTED)
    main(["format", "--write", name])
    assert (project / name).read_text(encoding="utf-8") == CLEAN


def test_lint_fail_level_option(project: Path) -> None:
    # A missing strict_types declaration is a warning: passes by default, fails at level warning.
    name = write(project, CLEAN.replace("declare(strict_types=1);\n\n", ""))
    assert main(["lint", name]) == 0
    assert main(["lint", "--minimum-fail-level=warning", name]) == 1


def test_global_option_is_accepted(project: Path) -> None:
    assert main(["lint", "--php-version=8.2", write(project, CLEAN)]) == 0


def test_excluded_file_passes(project: Path) -> None:
    assert main(["lint", write(project, SYNTAX_ERROR, "legacy/Old.php")]) == 0


# --- through Git -------------------------------------------------------------------------------------


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **ENV}
    return subprocess.run(["git", *args], cwd=repo, env=env, check=check, capture_output=True, text=True)


@pytest.fixture
def repo(project: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    git(project, "init", "-q", "-b", "main")
    hooks = tmp_path_factory.mktemp("hooks")
    src = Path(__file__).resolve().parents[1] / "src"
    # Stand-in for pre-commit: pass the staged PHP files, abort the commit on a non-zero exit.
    script = hooks / "pre-commit"
    script.write_text(
        "#!/bin/sh\n"
        "files=$(git diff --cached --name-only --diff-filter=ACMR -- '*.php')\n"
        '[ -z "$files" ] && exit 0\n'
        f'PYTHONPATH="{src}" "{sys.executable}" -m mago_pre_commit analyze $files\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    git(project, "config", "core.hooksPath", str(hooks))
    git(project, "add", ".")
    git(project, "commit", "-q", "-m", "Initial")
    return project


def test_commit_with_clean_file(repo: Path) -> None:
    git(repo, "add", write(repo, CLEAN))
    assert git(repo, "commit", "-m", "Add welcome", check=False).returncode == 0


def test_commit_with_error_is_blocked(repo: Path) -> None:
    git(repo, "add", write(repo, TYPE_ERROR))
    result = git(repo, "commit", "-m", "Add welcome", check=False)
    assert result.returncode != 0
    assert "invalid-return-statement" in result.stdout + result.stderr
    assert git(repo, "log", "--format=%s").stdout.split() == ["Initial"]
