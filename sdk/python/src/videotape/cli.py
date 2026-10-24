"""The `videotape` command.

    videotape intent module:app     prints the app's intent JSON
    videotape check module:app      prints what check finds; exits 1 on errors
    videotape schema                prints the intent document's JSON Schema
    videotape serve module:app --engine ws://...   serves the app to an engine (the app protocol)

`module:app` names a module and the `vt.app(...)` in it (`app` when left out). The module is
imported from the current directory, or from `--app-dir`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from .check import check
from .intent import App
from .records import RecordError


class UsageError(Exception):
    pass


def load(target: str, app_dir: str) -> App:
    module_name, _, attr = target.partition(":")
    if not module_name:
        raise UsageError(f"{target!r}: expected module:app, such as app:app")
    sys.path.insert(0, str(Path(app_dir).resolve()))
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise UsageError(f"cannot import {module_name}: {e}") from None
    value = getattr(module, attr or "app", None)
    if not isinstance(value, App):
        raise UsageError(f"{module_name}:{attr or 'app'} is not a vt.app(...)")
    return value


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="videotape", description="Videotape's Python SDK.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("intent", "print the app's intent JSON"), ("check", "check the app")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("target", metavar="module:app")
        sub.add_argument("--app-dir", default=".", help="where to import the module from (default: .)")
        if name == "check":
            sub.add_argument("--json", action="store_true", help="print diagnostics as JSON")
    commands.add_parser("schema", help="print the intent document's JSON Schema")
    sub = commands.add_parser("serve", help="serve the app to an engine over the app protocol")
    sub.add_argument("target", metavar="module:app")
    sub.add_argument("--app-dir", default=".", help="where to import the module from (default: .)")
    sub.add_argument("--engine", required=True, help="the engine's app endpoint, such as ws://127.0.0.1:8787/app")
    sub.add_argument("--once", action="store_true", help="exit when the connection ends instead of reconnecting")
    args = parser.parse_args(argv)

    if args.command == "schema":
        from .spec import intent_schema

        print(_dump(intent_schema()))
        return 0
    try:
        app = load(args.target, args.app_dir)
    except UsageError as e:
        print(f"videotape: {e}", file=sys.stderr)
        return 2

    if args.command == "serve":
        from .serve import main as serve_main

        return serve_main(app, args.engine, retry=not args.once)

    if args.command == "intent":
        try:
            print(_dump(app.intent()))
        except RecordError as e:
            print(f"videotape: {e}", file=sys.stderr)
            return 1
        return 0

    diagnostics = check(app)
    errors = sum(1 for d in diagnostics if d.level == "error")
    if args.json:
        print(_dump([d.to_json() for d in diagnostics]))
    else:
        for d in diagnostics:
            print(d)
        warnings = len(diagnostics) - errors
        if diagnostics:
            print(f"{errors} error{'s' * (errors != 1)}, {warnings} warning{'s' * (warnings != 1)}")
        else:
            print(f"{app.name}: no problems")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
