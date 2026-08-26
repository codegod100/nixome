from __future__ import annotations

import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

VARIABLE = re.compile(r"%\{([A-Za-z0-9_-]+)\}")
COMMAND_GROUPS = (
    "configure-commands",
    "build-commands",
    "install-commands",
    "strip-commands",
)


class TranslationError(Exception):
    """An unsupported or invalid BuildStream construct."""


def _yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise TranslationError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise TranslationError(f"{path} must contain a YAML mapping")
    return value


def _safe_relative(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise TranslationError(f"{label} must stay within the project: {value!r}")
    return str(path)


def _dependency_name(value: Any, owner: str) -> tuple[str, str]:
    if isinstance(value, str):
        return value, "build"
    if not isinstance(value, dict) or not isinstance(value.get("filename"), str):
        raise TranslationError(f"{owner}: malformed dependency {value!r}")
    dep_type = value.get("type", "build")
    if dep_type not in ("build", "run", "all"):
        raise TranslationError(f"{owner}: unsupported dependency type {dep_type!r}")
    return value["filename"], dep_type


def translate(project_dir: Path, target: str) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    project = _yaml(project_dir / "project.conf")
    element_path = project.get("element-path", "elements")
    if not isinstance(element_path, str):
        raise TranslationError("project.conf: element-path must be a string")
    element_root = project_dir / _safe_relative(element_path, "element-path")
    project_variables = project.get("variables", {})
    if not isinstance(project_variables, dict):
        raise TranslationError("project.conf: variables must be a mapping")

    elements: dict[str, Any] = {}
    visiting: list[str] = []

    def visit(name: str) -> None:
        name = _safe_relative(name, "element name")
        if name in elements:
            return
        if name in visiting:
            cycle = " -> ".join([*visiting, name])
            raise TranslationError(f"dependency cycle: {cycle}")
        visiting.append(name)

        document = _yaml(element_root / name)
        kind = document.get("kind")
        if kind != "manual":
            raise TranslationError(
                f"{name}: unsupported kind {kind!r}; proof of concept supports 'manual'"
            )

        build_deps: list[str] = []
        run_deps: list[str] = []
        for raw_dep in document.get("depends", []):
            dep, dep_type = _dependency_name(raw_dep, name)
            dep = _safe_relative(dep, f"{name} dependency")
            visit(dep)
            if dep_type in ("build", "all"):
                build_deps.append(dep)
            if dep_type in ("run", "all"):
                run_deps.append(dep)

        variables = {str(key): str(value) for key, value in project_variables.items()}
        element_variables = document.get("variables", {})
        if not isinstance(element_variables, dict):
            raise TranslationError(f"{name}: variables must be a mapping")
        variables.update({str(key): str(value) for key, value in element_variables.items()})

        sources = []
        for source in document.get("sources", []):
            if not isinstance(source, dict) or source.get("kind") != "local":
                source_kind = source.get("kind") if isinstance(source, dict) else None
                raise TranslationError(
                    f"{name}: unsupported source kind {source_kind!r}; "
                    "proof of concept supports 'local'"
                )
            source_path = source.get("path")
            if not isinstance(source_path, str):
                raise TranslationError(f"{name}: local source requires a path")
            sources.append(
                {
                    "path": _safe_relative(source_path, f"{name} source"),
                    "directory": _safe_relative(
                        str(source.get("directory", ".")), f"{name} source directory"
                    ),
                }
            )

        config = document.get("config", {})
        if not isinstance(config, dict):
            raise TranslationError(f"{name}: config must be a mapping")
        commands: list[str] = []
        for group in COMMAND_GROUPS:
            values = config.get(group, [])
            if not isinstance(values, list) or not all(
                isinstance(command, str) for command in values
            ):
                raise TranslationError(f"{name}: {group} must be a list of strings")
            commands.extend(values)

        elements[name] = {
            "kind": kind,
            "buildDependencies": build_deps,
            "runDependencies": run_deps,
            "sources": sources,
            "variables": variables,
            "commands": commands,
        }
        visiting.pop()

    visit(target)
    return {
        "formatVersion": 1,
        "project": str(project.get("name", project_dir.name)),
        "target": _safe_relative(target, "target"),
        "elements": elements,
    }


def audit(project_dir: Path, target: str) -> dict[str, Any]:
    """Inventory a target without claiming that unsupported kinds can build.

    Junction dependencies are reported as boundaries. Resolving them requires
    BuildStream option, override, and project-include semantics, so the audit
    never silently treats them as ordinary local elements.
    """

    project_dir = project_dir.resolve()
    project = _yaml(project_dir / "project.conf")
    element_path = project.get("element-path", "elements")
    if not isinstance(element_path, str):
        raise TranslationError("project.conf: element-path must be a string")
    element_root = project_dir / _safe_relative(element_path, "element-path")

    kinds: Counter[str] = Counter()
    source_kinds: Counter[str] = Counter()
    external_dependencies: set[str] = set()
    composition_directives: list[dict[str, str]] = []
    elements: dict[str, dict[str, Any]] = {}
    visiting: list[str] = []

    def visit(name: str) -> None:
        name = _safe_relative(name, "element name")
        if name in elements:
            return
        if name in visiting:
            cycle = " -> ".join([*visiting, name])
            raise TranslationError(f"dependency cycle: {cycle}")
        visiting.append(name)
        document = _yaml(element_root / name)
        kind = str(document.get("kind", "<missing>"))
        kinds[kind] += 1

        dependencies: list[str] = []
        for group in ("depends", "build-depends", "runtime-depends"):
            raw_dependencies = document.get(group, [])
            if isinstance(raw_dependencies, dict) and any(
                str(key).startswith("(") for key in raw_dependencies
            ):
                composition_directives.append(
                    {
                        "element": name,
                        "group": group,
                        "directive": ",".join(
                            sorted(str(key) for key in raw_dependencies)
                        ),
                    }
                )
                continue
            if not isinstance(raw_dependencies, list):
                raise TranslationError(f"{name}: {group} must be a list")
            for raw_dependency in raw_dependencies:
                if (
                    isinstance(raw_dependency, dict)
                    and "filename" not in raw_dependency
                    and any(str(key).startswith("(") for key in raw_dependency)
                ):
                    composition_directives.append(
                        {
                            "element": name,
                            "group": group,
                            "directive": ",".join(
                                sorted(str(key) for key in raw_dependency)
                            ),
                        }
                    )
                    continue
                dependency, _ = _dependency_name(raw_dependency, name)
                if ":" in dependency:
                    external_dependencies.add(dependency)
                    continue
                dependency = _safe_relative(dependency, f"{name} dependency")
                dependencies.append(dependency)
                visit(dependency)

        element_source_kinds = []
        raw_sources = document.get("sources", [])
        if isinstance(raw_sources, dict) and any(
            str(key).startswith("(") for key in raw_sources
        ):
            composition_directives.append(
                {
                    "element": name,
                    "group": "sources",
                    "directive": ",".join(sorted(str(key) for key in raw_sources)),
                }
            )
            raw_sources = []
        if not isinstance(raw_sources, list):
            raise TranslationError(f"{name}: sources must be a list")
        for source in raw_sources:
            if (
                isinstance(source, dict)
                and "kind" not in source
                and any(str(key).startswith("(") for key in source)
            ):
                composition_directives.append(
                    {
                        "element": name,
                        "group": "sources",
                        "directive": ",".join(sorted(str(key) for key in source)),
                    }
                )
                continue
            source_kind = (
                str(source.get("kind", "<missing>"))
                if isinstance(source, dict)
                else "<malformed>"
            )
            source_kinds[source_kind] += 1
            element_source_kinds.append(source_kind)

        elements[name] = {
            "kind": kind,
            "dependencies": sorted(set(dependencies)),
            "sourceKinds": element_source_kinds,
        }
        visiting.pop()

    visit(target)
    supported_kinds = {"manual"}
    supported_source_kinds = {"local"}
    return {
        "formatVersion": 1,
        "mode": "audit",
        "project": str(project.get("name", project_dir.name)),
        "target": _safe_relative(target, "target"),
        "summary": {
            "localElementCount": len(elements),
            "elementKinds": dict(sorted(kinds.items())),
            "sourceKinds": dict(sorted(source_kinds.items())),
            "unsupportedElementKinds": sorted(set(kinds) - supported_kinds),
            "unsupportedSourceKinds": sorted(set(source_kinds) - supported_source_kinds),
            "junctionDependencyCount": len(external_dependencies),
            "compositionDirectiveCount": len(composition_directives),
        },
        "externalDependencies": sorted(external_dependencies),
        "compositionDirectives": sorted(
            composition_directives,
            key=lambda item: (item["element"], item["group"], item["directive"]),
        ),
        "elements": dict(sorted(elements.items())),
    }
