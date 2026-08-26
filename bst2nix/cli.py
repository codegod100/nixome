from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .translator import TranslationError, translate


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="bst2nix",
        description="Translate a BuildStream project into a Nix-consumable graph",
    )
    result.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = result.add_subparsers(dest="command", required=True)
    lock = commands.add_parser("lock", help="resolve an element dependency graph")
    lock.add_argument("project", type=Path, help="directory containing project.conf")
    lock.add_argument("element", help="target element, for example image.bst")
    lock.add_argument("-o", "--output", type=Path, help="output file (default: stdout)")
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        graph = translate(args.project, args.element)
    except TranslationError as error:
        print(f"bst2nix: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    rendered = json.dumps(graph, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
