"""Locate the mago executable for the repository being committed to."""

import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

ENV_VARIABLE = "MAGO_BINARY"


def composer_bin_dir(root: Path) -> Path:
    """The Composer bin directory, honouring `config.bin-dir` and `config.vendor-dir`."""
    config: dict[str, object] = {}
    try:
        data = json.loads((root / "composer.json").read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("config"), dict):
            config = data["config"]
    except (OSError, ValueError):
        pass
    bin_dir = config.get("bin-dir")
    if isinstance(bin_dir, str) and bin_dir:
        return root / bin_dir
    vendor_dir = config.get("vendor-dir")
    return root / (vendor_dir if isinstance(vendor_dir, str) and vendor_dir else "vendor") / "bin"


def resolve(
    root: Path, explicit: str | None = None, environ: Mapping[str, str] | None = None
) -> list[str] | None:
    """Return the command that starts mago, or None if there is none.

    Order: `--mago` option, `MAGO_BINARY` environment variable, the project's Composer
    installation (`carthage-software/mago`, a PHP launcher, so it needs `php`), then `mago` on PATH.
    The Composer installation comes before PATH so every developer runs the version the project pins.
    """
    environ = os.environ if environ is None else environ
    for candidate in (explicit, environ.get(ENV_VARIABLE)):
        if candidate:
            return [candidate]

    launcher = composer_bin_dir(root) / "mago"
    php = shutil.which("php")
    if launcher.is_file() and php:
        return [php, str(launcher)]

    found = shutil.which("mago")
    return [found] if found else None
