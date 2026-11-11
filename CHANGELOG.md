# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-11-11

### Added

- Hooks `mago-lint`, `mago-analyze` and `mago-format` for the staged PHP files. A failing check
  stops the commit.
- `mago-format` shows the diff without touching the file; `--write` formats in place.
- mago is looked up via `--mago`, `$MAGO_BINARY`, the project's Composer bin directory, then `PATH`.
- Global mago options in the hook `args` are moved in front of the subcommand.
- `mago-analyze` refuses to run without a `mago.toml`, instead of reporting every class outside the
  staged files as missing.

[Unreleased]: https://github.com/davidzach/mago-pre-commit/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/davidzach/mago-pre-commit/releases/tag/v1.0.0
