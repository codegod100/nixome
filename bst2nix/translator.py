from __future__ import annotations

import re
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
