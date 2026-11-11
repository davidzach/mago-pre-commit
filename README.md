# mago-pre-commit

[![test](https://github.com/davidzach/mago-pre-commit/actions/workflows/test.yml/badge.svg)](https://github.com/davidzach/mago-pre-commit/actions/workflows/test.yml)

[pre-commit](https://pre-commit.com) hooks that check staged PHP files with [mago](https://mago.carthage.software) and **stop the commit when a check fails**.

```
$ git commit -m "Add greeter"
mago format..............................................................Passed
mago lint................................................................Passed
mago analyze.............................................................Failed
- hook id: mago-analyze
- exit code: 1

src/Greeter.php:13:16: error[invalid-return-statement]: Invalid return type for function
`App\Greeter::greet`: expected `int`, but found `string`.
```

| Hook | Runs | Fails when |
|---|---|---|
| `mago-format` | `mago format --dry-run` | a staged file is not formatted; prints the diff, changes nothing |
| `mago-lint` | `mago lint` | an issue reaches the fail level (default: `error`) |
| `mago-analyze` | `mago analyze` | the static analysis reports an error, with the whole project as context |

Only staged `.php` files are checked. pre-commit hides unstaged changes while the hooks run, so what is checked is exactly what gets committed.

## Installation

1. Install mago — in the project (preferred, everyone uses the same version) or on your machine:

   ```bash
   composer require --dev carthage-software/mago   # needs php on the host
   brew install mago                               # or see https://mago.carthage.software
   ```

2. Create a `mago.toml` in the repository root (`mago init`). `mago-analyze` refuses to run without one, see [below](#mago-analyze-needs-a-magotoml).

3. Add the hooks:

   ```yaml
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/davidzach/mago-pre-commit
       rev: v1.0.0
       hooks:
         - id: mago-format
         - id: mago-lint
         - id: mago-analyze
   ```

   ```bash
   pre-commit install
   ```

Pick the hooks you want; each one works on its own. Keep `rev` current with `pre-commit autoupdate`.

### Which mago runs

The first match wins:

1. `--mago=PATH` in the hook's `args`
2. the environment variable `MAGO_BINARY`
3. the project's Composer installation (`vendor/bin/mago`, honouring `config.bin-dir`/`vendor-dir` in `composer.json`), started with the `php` on your `PATH`
4. `mago` on your `PATH`

If none is found, the hook fails and says how to install mago. The Composer package downloads the matching binary on its first run.

## Options

Hook `args` are passed to mago. Global mago options (`--config`, `--php-version`, `--workspace`, `--threads`, `--colors`, `--no-version-check`, `--allow-unsupported-php-version`) are moved in front of the subcommand automatically.

pre-commit appends the file names after the `args`, so **options with a value need the form `--option=value`** — or end the list with `--`:

```yaml
      - id: mago-lint
        args: [--minimum-fail-level=warning]        # also fail on warnings
      - id: mago-analyze
        args: [--baseline, mago-baseline.toml, --]  # same as --baseline=mago-baseline.toml
      - id: mago-format
        args: [--write]                             # format in place instead of only showing the diff
```

| Option | Hook | Effect |
|---|---|---|
| `--mago=PATH` | all | mago executable to use |
| `--write` | `mago-format` | rewrites the files. pre-commit still fails the commit because files changed; review, `git add`, commit again. |
| `--minimum-fail-level=…` | lint, analyze | `note`, `help`, `warning` or `error` (default, or what `mago.toml` sets) |
| `--baseline=FILE` | lint, analyze | ignore the issues recorded in a baseline, see below |
| `--php-version=8.3` | all | the PHP version to parse and analyse for, if `mago.toml` does not set it |

Settings that belong to the project (rules, PHP version, excludes, fail levels) are better placed in `mago.toml`: the editor, CI and the hook then agree.

## `mago-analyze` needs a `mago.toml`

The analyzer resolves classes, functions and constants across the project. Given only the staged files without a configuration, mago knows nothing else and reports every class defined elsewhere as missing. With a `mago.toml`, mago loads the configured `[source] paths` (and `includes`, e.g. `vendor`) as context and reports issues only for the staged files.

```toml
# mago.toml
php-version = "8.3"

[source]
paths = ["src", "packages"]
includes = ["vendor"]
excludes = ["var", "public/typo3temp"]
```

Files under `excludes` are skipped even when they are staged.

## Existing code with many issues

Record the current state in a baseline, then only new issues block a commit:

```bash
mago analyze --generate-baseline --baseline=mago-analyze-baseline.toml
mago lint --generate-baseline --baseline=mago-lint-baseline.toml
```

Commit the baseline files and point the configuration (or the hook `args`) at them.

## Skipping

```bash
SKIP=mago-analyze git commit -m "…"   # skip one hook
git commit --no-verify -m "…"         # skip all hooks
```

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install --group dev .
.venv/bin/python -m pytest
.venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy
```

The integration tests need `mago` on `PATH` and are skipped without it. CI runs them on Linux and macOS with a pinned mago release, plus a job that installs the hooks through pre-commit and checks that a commit with a type error is rejected.

## License

MIT
