"""Command line entry point, called by pre-commit with the staged PHP files."""

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mago_pre_commit import __version__, binary

COMMANDS = ("lint", "analyze", "format")
PROG = "mago-hook"

# mago accepts these only before the subcommand.
GLOBAL_VALUE_OPTIONS = {"--workspace", "--config", "--php-version", "--threads", "--colors"}
GLOBAL_FLAGS = {"--allow-unsupported-php-version", "--no-version-check"}

# Mago finds these in the workspace without --config.
CONFIG_FILES = ("mago.toml", "mago.dist.toml")

# Options of `mago format` that already choose what happens to the files.
FORMAT_MODES = {"--check", "-c", "--dry-run", "-d", "--stdin-input", "-i", "--staged", "-s"}

USAGE = f"""usage: {PROG} {{{",".join(COMMANDS)}}} [--mago=PATH] [--write] [MAGO OPTIONS] [--] [FILE ...]

Runs `mago <command>` on the given files and exits with mago's status, so a failing check blocks
the commit. Options with a value need the form --option=value, or end the options with `--`.

  --mago=PATH   mago executable to use (default: $MAGO_BINARY, Composer's bin dir, PATH)
  --write       format only: rewrite the files instead of showing the diff
"""


class UsageError(Exception):
    pass


@dataclass
class Invocation:
    command: str
    mago: str | None = None
    write: bool = False
    global_options: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


def parse(argv: Sequence[str]) -> Invocation:
    """Split pre-commit's argument list into wrapper options, mago options and files.

    pre-commit appends the file names after the configured `args`. Without a `--` separator, every
    argument starting with `-` is an option and everything else a file, so options that take a
    value must be written as `--option=value`. With `--`, everything before it is an option.
    """
    if not argv or argv[0] not in COMMANDS:
        raise UsageError(f"expected one of {', '.join(COMMANDS)} as first argument")
    invocation = Invocation(command=argv[0])
    rest = list(argv[1:])

    if "--" in rest:
        split = rest.index("--")
        raw_options, invocation.files = rest[:split], rest[split + 1 :]
    else:
        raw_options = [arg for arg in rest if arg.startswith("-")]
        invocation.files = [arg for arg in rest if not arg.startswith("-")]

    options = iter(raw_options)
    for option in options:
        name, has_value, value = option.partition("=")
        if name == "--mago":
            invocation.mago = value if has_value else next(options, None)
            if not invocation.mago:
                raise UsageError("--mago needs a path")
        elif name == "--write":
            if invocation.command != "format":
                raise UsageError("--write only applies to format")
            invocation.write = True
        elif name in GLOBAL_FLAGS:
            invocation.global_options.append(option)
        elif name in GLOBAL_VALUE_OPTIONS:
            invocation.global_options.append(option)
            if not has_value:
                following = next(options, None)
                if following is None:
                    raise UsageError(f"{name} needs a value")
                invocation.global_options.append(following)
        else:
            invocation.options.append(option)
    return invocation


def command_line(invocation: Invocation, executable: list[str]) -> list[str]:
    options = list(invocation.options)
    chosen_mode = any(option.partition("=")[0] in FORMAT_MODES for option in options)
    if invocation.command == "format" and not invocation.write and not chosen_mode:
        # Prints the diff and exits 1 when a file is not formatted; never touches the file.
        options.insert(0, "--dry-run")
    return [*executable, *invocation.global_options, invocation.command, *options, *invocation.files]


def has_config(invocation: Invocation, root: Path) -> bool:
    if any(option.startswith("--config") for option in invocation.global_options):
        return True
    workspace = root
    for index, option in enumerate(invocation.global_options):
        name, has_value, value = option.partition("=")
        if name == "--workspace":
            workspace = root / (value if has_value else invocation.global_options[index + 1])
    return any((workspace / name).is_file() for name in CONFIG_FILES)


def _error(message: str) -> int:
    print(f"{PROG}: {message}", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] in (["-h"], ["--help"]):
        print(USAGE, end="")
        return 0
    if argv[:1] == ["--version"]:
        print(f"{PROG} {__version__}")
        return 0

    try:
        invocation = parse(argv)
    except UsageError as error:
        return _error(f"{error}\n\n{USAGE}")

    if not invocation.files:
        return 0

    root = Path.cwd()
    if invocation.command == "analyze" and not has_config(invocation, root):
        return _error(
            "analyze needs a mago.toml whose [source] paths cover the whole project.\n"
            "Without it mago only sees the staged files and reports every class defined elsewhere\n"
            "as missing. Create one with `mago init`, or pass --config=PATH in the hook's args."
        )

    executable = binary.resolve(root, invocation.mago)
    if executable is None:
        return _error(
            "mago not found. Install it in the project (`composer require --dev carthage-software/mago`,\n"
            "needs php on the host), globally (`brew install mago`, see https://mago.carthage.software),\n"
            f"or point ${binary.ENV_VARIABLE} or --mago=PATH at the binary."
        )

    try:
        return subprocess.run(command_line(invocation, executable), check=False).returncode
    except OSError as error:
        return _error(f"cannot run {executable[0]}: {error}")
