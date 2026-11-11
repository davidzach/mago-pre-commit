"""Unit tests: argument handling, command line, config detection, binary lookup. No mago needed."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from mago_pre_commit import binary
from mago_pre_commit.cli import Invocation, UsageError, command_line, has_config, main, parse

# --- parse -------------------------------------------------------------------------------------------


def test_files_and_options_without_separator() -> None:
    invocation = parse(["lint", "--minimum-fail-level=warning", "src/A.php", "src/B.php"])
    assert invocation == Invocation(
        command="lint", options=["--minimum-fail-level=warning"], files=["src/A.php", "src/B.php"]
    )


def test_separator_allows_option_values() -> None:
    invocation = parse(["lint", "--baseline", "mago-baseline.toml", "--", "src/A.php"])
    assert invocation.options == ["--baseline", "mago-baseline.toml"]
    assert invocation.files == ["src/A.php"]


def test_global_options_are_hoisted() -> None:
    invocation = parse(["analyze", "--php-version=8.2", "--no-version-check", "--sort", "a.php"])
    assert invocation.global_options == ["--php-version=8.2", "--no-version-check"]
    assert invocation.options == ["--sort"]


def test_global_option_with_separate_value() -> None:
    invocation = parse(["lint", "--config", "build/mago.toml", "--", "a.php"])
    assert invocation.global_options == ["--config", "build/mago.toml"]


def test_global_option_missing_value() -> None:
    with pytest.raises(UsageError, match="--config needs a value"):
        parse(["lint", "--config", "--"])


@pytest.mark.parametrize("args", [["--mago=/opt/mago"], ["--mago", "/opt/mago", "--"]])
def test_mago_option(args: list[str]) -> None:
    assert parse(["lint", *args, "a.php"]).mago == "/opt/mago"


@pytest.mark.parametrize("args", [["--mago="], ["--mago", "--"]])
def test_mago_option_needs_path(args: list[str]) -> None:
    with pytest.raises(UsageError, match="--mago needs a path"):
        parse(["lint", *args])


def test_write_only_for_format() -> None:
    assert parse(["format", "--write", "a.php"]).write
    with pytest.raises(UsageError, match="--write only applies to format"):
        parse(["lint", "--write", "a.php"])


@pytest.mark.parametrize("argv", [[], ["fix"], ["a.php"]])
def test_unknown_command(argv: list[str]) -> None:
    with pytest.raises(UsageError, match="expected one of"):
        parse(argv)


# --- command_line ------------------------------------------------------------------------------------


def test_command_line_order() -> None:
    invocation = parse(["lint", "--php-version=8.2", "--sort", "a.php"])
    assert command_line(invocation, ["mago"]) == ["mago", "--php-version=8.2", "lint", "--sort", "a.php"]


def test_format_defaults_to_dry_run() -> None:
    assert command_line(parse(["format", "a.php"]), ["mago"]) == ["mago", "format", "--dry-run", "a.php"]


@pytest.mark.parametrize("mode", ["--check", "-d"])
def test_format_keeps_explicit_mode(mode: str) -> None:
    assert command_line(parse(["format", mode, "a.php"]), ["mago"]) == ["mago", "format", mode, "a.php"]


def test_format_write() -> None:
    assert command_line(parse(["format", "--write", "a.php"]), ["mago"]) == ["mago", "format", "a.php"]


# --- has_config --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["mago.toml", "mago.dist.toml"])
def test_config_in_root(tmp_path: Path, name: str) -> None:
    assert not has_config(parse(["analyze", "a.php"]), tmp_path)
    (tmp_path / name).write_text("", encoding="utf-8")
    assert has_config(parse(["analyze", "a.php"]), tmp_path)


def test_config_option(tmp_path: Path) -> None:
    assert has_config(parse(["analyze", "--config=x.toml", "a.php"]), tmp_path)


@pytest.mark.parametrize("args", [["--workspace=app"], ["--workspace", "app", "--"]])
def test_config_in_workspace(tmp_path: Path, args: list[str]) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "mago.toml").write_text("", encoding="utf-8")
    assert has_config(parse(["analyze", *args, "a.php"]), tmp_path)
    assert not has_config(parse(["analyze", "a.php"]), tmp_path)


# --- binary ------------------------------------------------------------------------------------------


def test_bin_dir_default(tmp_path: Path) -> None:
    assert binary.composer_bin_dir(tmp_path) == tmp_path / "vendor" / "bin"


@pytest.mark.parametrize(
    ("config", "expected"),
    [({"vendor-dir": "lib"}, "lib/bin"), ({"bin-dir": "tools"}, "tools"), ({"vendor-dir": 3}, "vendor/bin")],
)
def test_bin_dir_from_composer(tmp_path: Path, config: dict[str, object], expected: str) -> None:
    (tmp_path / "composer.json").write_text(json.dumps({"config": config}), encoding="utf-8")
    assert binary.composer_bin_dir(tmp_path) == tmp_path / expected


def test_bin_dir_broken_composer_json(tmp_path: Path) -> None:
    (tmp_path / "composer.json").write_text("{", encoding="utf-8")
    assert binary.composer_bin_dir(tmp_path) == tmp_path / "vendor" / "bin"


def fake_which(found: dict[str, str]) -> object:
    return lambda name: found.get(name)


def test_resolve_explicit_then_env(tmp_path: Path) -> None:
    assert binary.resolve(tmp_path, "/a/mago", {"MAGO_BINARY": "/b/mago"}) == ["/a/mago"]
    assert binary.resolve(tmp_path, None, {"MAGO_BINARY": "/b/mago"}) == ["/b/mago"]


def test_resolve_composer_before_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = tmp_path / "vendor" / "bin" / "mago"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("<?php", encoding="utf-8")
    monkeypatch.setattr("shutil.which", fake_which({"php": "/usr/bin/php", "mago": "/usr/bin/mago"}))
    assert binary.resolve(tmp_path, None, {}) == ["/usr/bin/php", str(launcher)]


def test_resolve_composer_needs_php(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = tmp_path / "vendor" / "bin" / "mago"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("<?php", encoding="utf-8")
    monkeypatch.setattr("shutil.which", fake_which({"mago": "/usr/bin/mago"}))
    assert binary.resolve(tmp_path, None, {}) == ["/usr/bin/mago"]


def test_resolve_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", fake_which({}))
    assert binary.resolve(tmp_path, None, {}) is None


# --- main --------------------------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(binary.ENV_VARIABLE, raising=False)
    return tmp_path


def test_help_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    assert "usage: mago-hook" in capsys.readouterr().out
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("mago-hook ")


def test_usage_error_blocks(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix"]) == 1
    assert "expected one of" in capsys.readouterr().err


def test_no_files_passes(project: Path) -> None:
    assert main(["lint"]) == 0


def test_analyze_without_config_blocks(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", "a.php"]) == 1
    assert "mago init" in capsys.readouterr().err


def test_missing_binary_blocks(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("shutil.which", fake_which({}))
    assert main(["lint", "a.php"]) == 1
    assert "mago not found" in capsys.readouterr().err


def test_unrunnable_binary_blocks(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["lint", f"--mago={project / 'missing'}", "a.php"]) == 1
    assert "cannot run" in capsys.readouterr().err


def test_exit_code_is_passed_through(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 3)

    monkeypatch.setattr("subprocess.run", run)
    assert main(["lint", "--mago=/x/mago", "a.php"]) == 3
    assert calls == [["/x/mago", "lint", "a.php"]]


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["mago_pre_commit", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("mago_pre_commit", run_name="__main__")
    assert exit_info.value.code == 0
