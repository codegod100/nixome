from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .graph import GraphError
from .build_plan import BuildPlanError
from .executor import ExecutionError
from .junction import JunctionError
from .oci import OciError
from .source_lock import SourceLockError
from .staging import StagingError
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
    audit = commands.add_parser(
        "audit", help="inventory the kinds needed by a real BuildStream target"
    )
    audit.add_argument("project", type=Path, help="directory containing project.conf")
    audit.add_argument("element", help="target element")
    audit.add_argument("-o", "--output", type=Path, help="output file (default: stdout)")
    graph = commands.add_parser(
        "lock-graph", help="lock a composed graph across pinned junction checkouts"
    )
    graph.add_argument("project", type=Path)
    graph.add_argument("element")
    graph.add_argument("--options", type=Path, required=True)
    graph.add_argument(
        "--revision",
        action="append",
        default=[],
        metavar="PROJECT=REVISION",
        help="immutable project revision; repeat for every project",
    )
    graph.add_argument(
        "--project-url",
        action="append",
        default=[],
        metavar="PROJECT=URL",
        help="canonical repository URL; repeat for every project",
    )
    graph.add_argument(
        "--junction",
        action="append",
        default=[],
        metavar="ELEMENT=CHECKOUT",
    )
    graph.add_argument(
        "--junction-options",
        action="append",
        default=[],
        metavar="ELEMENT=JSON",
    )
    graph.add_argument("-o", "--output", type=Path)
    sources = commands.add_parser(
        "lock-sources", help="normalize and deduplicate graph source declarations"
    )
    sources.add_argument("graph", type=Path)
    sources.add_argument(
        "--aliases", action="append", default=[], metavar="PROJECT=YAML"
    )
    sources.add_argument("-o", "--output", type=Path)
    generated = commands.add_parser(
        "generate-buck-sources", help="generate one Buck2 target per Git source"
    )
    generated.add_argument("source_lock", type=Path)
    generated.add_argument("-o", "--output", type=Path, required=True)
    oci = commands.add_parser(
        "export-oci", help="export a root filesystem as a deterministic OCI layout"
    )
    oci.add_argument("rootfs", type=Path)
    oci.add_argument("-o", "--output", type=Path, required=True)
    oci.add_argument("--architecture", choices=["amd64", "arm64"], default="amd64")
    oci.add_argument("--reference", default="gnomeos:latest")
    oci.add_argument("--label", action="append", default=[], metavar="NAME=VALUE")
    stage = commands.add_parser(
        "stage-sources", help="stage an element's locked, materialized sources"
    )
    stage.add_argument("source_lock", type=Path)
    stage.add_argument("element")
    stage.add_argument("--materialized", type=Path, action="append", required=True)
    stage.add_argument("-o", "--output", type=Path, required=True)
    plan = commands.add_parser(
        "build-plan", help="emit the native execution plan for a locked element"
    )
    plan.add_argument("graph", type=Path)
    plan.add_argument("element")
    plan.add_argument("-o", "--output", type=Path)
    execute = commands.add_parser(
        "execute-plan", help="execute a native element plan without BuildStream"
    )
    execute.add_argument("plan", type=Path)
    execute.add_argument("--source", type=Path, required=True)
    execute.add_argument(
        "--dependency", action="append", default=[], metavar="ELEMENT=ARTIFACT"
    )
    execute.add_argument("-o", "--output", type=Path, required=True)
    generated_elements = commands.add_parser(
        "generate-buck-elements",
        help="generate the executable native element DAG",
    )
    generated_elements.add_argument("graph", type=Path)
    generated_elements.add_argument("source_lock", type=Path)
    generated_elements.add_argument("-o", "--output", type=Path, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "generate-buck-elements":
            from .element_generator import generate_buck_elements

            rendered = generate_buck_elements(
                json.loads(args.graph.read_text(encoding="utf-8")),
                json.loads(args.source_lock.read_text(encoding="utf-8")),
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            return
        elif args.command == "execute-plan":
            from .executor import execute_plan

            dependencies = {}
            for assignment in args.dependency:
                if "=" not in assignment:
                    raise ExecutionError("--dependency requires ELEMENT=ARTIFACT")
                name, path = assignment.split("=", 1)
                dependencies[name] = Path(path)
            execute_plan(
                json.loads(args.plan.read_text(encoding="utf-8")),
                args.source,
                dependencies,
                args.output,
            )
            return
        elif args.command == "build-plan":
            from .build_plan import element_build_plan

            graph = element_build_plan(
                json.loads(args.graph.read_text(encoding="utf-8")), args.element
            )
        elif args.command == "stage-sources":
            from .staging import stage_element_sources

            stage_element_sources(
                json.loads(args.source_lock.read_text(encoding="utf-8")),
                args.element,
                args.materialized,
                args.output,
            )
            return
        elif args.command == "export-oci":
            from .oci import export_oci

            labels = {}
            for assignment in args.label:
                if "=" not in assignment:
                    raise OciError("--label requires NAME=VALUE")
                key, value = assignment.split("=", 1)
                if not key:
                    raise OciError("--label requires NAME=VALUE")
                labels[key] = value
            export_oci(
                args.rootfs,
                args.output,
                architecture=args.architecture,
                reference=args.reference,
                labels=labels,
            )
            return
        elif args.command == "generate-buck-sources":
            from .buck_generator import generate_buck_sources

            rendered = generate_buck_sources(
                json.loads(args.source_lock.read_text(encoding="utf-8"))
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            return
        elif args.command == "lock-sources":
            import yaml

            from .source_lock import lock_sources

            aliases = {}
            for assignment in args.aliases:
                if "=" not in assignment:
                    raise TranslationError("--aliases requires PROJECT=YAML")
                project, path = assignment.split("=", 1)
                value = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
                if set(value) == {"aliases"}:
                    value = value["aliases"]
                if not isinstance(value, dict) or not all(
                    isinstance(key, str) and isinstance(item, str)
                    for key, item in value.items()
                ):
                    raise TranslationError(f"invalid aliases file for {project}")
                aliases[project] = value
            graph = lock_sources(
                json.loads(args.graph.read_text(encoding="utf-8")), aliases
            )
        elif args.command == "lock-graph":
            from .graph import lock_graph
            from .junction import JunctionResolver, load_project

            def assignments(values: list[str], label: str) -> dict[str, str]:
                result = {}
                for value in values:
                    if "=" not in value:
                        raise TranslationError(f"{label} requires NAME=VALUE")
                    key, item = value.split("=", 1)
                    if not key or not item:
                        raise TranslationError(f"{label} requires NAME=VALUE")
                    result[key] = item
                return result

            options = json.loads(args.options.read_text(encoding="utf-8"))
            resolver = JunctionResolver(load_project(args.project, options))
            junction_options = assignments(
                args.junction_options, "--junction-options"
            )
            for element, checkout in assignments(
                args.junction, "--junction"
            ).items():
                option_path = junction_options.get(element)
                imported_options = (
                    json.loads(Path(option_path).read_text(encoding="utf-8"))
                    if option_path
                    else {}
                )
                resolver.add(element, Path(checkout), imported_options)
            resolver.compose_root()
            graph = lock_graph(
                resolver,
                args.element,
                project_revisions=assignments(args.revision, "--revision"),
                project_urls=assignments(args.project_url, "--project-url"),
            )
        elif args.command == "audit":
            from .translator import audit

            graph = audit(args.project, args.element)
        else:
            graph = translate(args.project, args.element)
    except (
        TranslationError,
        OSError,
        json.JSONDecodeError,
        GraphError,
        JunctionError,
        SourceLockError,
        OciError,
        StagingError,
        BuildPlanError,
        ExecutionError,
    ) as error:
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
