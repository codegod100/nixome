from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .composition import CompositionError, load_composed


class JunctionError(Exception):
    pass


@dataclass(frozen=True, order=True)
class ElementRef:
    project: str
    element: str

    def qualified(self) -> str:
        return f"{self.project}:{self.element}"


@dataclass(frozen=True)
class Project:
    name: str
    root: Path
    element_path: str
    options: dict[str, Any]
    variables: dict[str, Any]
    environment: dict[str, Any]


@dataclass(frozen=True)
class Junction:
    element: str
    project: Project
    overrides: dict[str, str]
    source_url: str
    source_ref: str


def _safe_relative(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise JunctionError(f"{label} escapes its project: {value!r}")
    return str(path)


def _raw_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise JunctionError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise JunctionError(f"{path} must contain a mapping")
    return value


def load_project(
    root: Path,
    options: dict[str, Any],
    *,
    compose: bool = False,
) -> Project:
    root = root.resolve()
    if compose:
        try:
            config = load_composed(
                root / "project.conf",
                project_root=root,
                options=options,
            )
        except CompositionError as error:
            raise JunctionError(str(error)) from error
    else:
        # The root project may include files through junctions which have not
        # been registered yet. Junction projects are loaded compositionally
        # below, once their checkout is available.
        config = _raw_yaml(root / "project.conf")
    if not isinstance(config, dict):
        raise JunctionError(f"{root}/project.conf must contain a mapping")
    name = config.get("name")
    if not isinstance(name, str):
        raise JunctionError(f"{root}/project.conf has no project name")
    element_path = config.get("element-path", "elements")
    if not isinstance(element_path, str):
        raise JunctionError(f"{root}/project.conf has invalid element-path")
    variables = config.get("variables", {})
    environment = config.get("environment", {})
    if not isinstance(variables, dict) or not isinstance(environment, dict):
        raise JunctionError(
            f"{root}/project.conf has invalid variables or environment"
        )
    return Project(
        name=name,
        root=root,
        element_path=_safe_relative(element_path, "element-path"),
        options=dict(options),
        variables=dict(variables),
        environment=dict(environment),
    )


class JunctionResolver:
    """Resolve cross-project references against explicitly pinned checkouts."""

    def __init__(self, root: Project):
        self.root = root
        self._junctions: dict[str, Junction] = {}

    def add(self, junction_element: str, checkout: Path, options: dict[str, Any]) -> None:
        junction_element = _safe_relative(junction_element, "junction element")
        element_file = self.root.root / self.root.element_path / junction_element
        document = _raw_yaml(element_file)
        if document.get("kind") != "junction":
            raise JunctionError(f"{junction_element} is not a junction")

        sources = document.get("sources", [])
        git_sources = [
            source
            for source in sources
            if isinstance(source, dict)
            and source.get("kind") in {"git", "git_repo", "git_module"}
        ]
        if len(git_sources) != 1:
            raise JunctionError(
                f"{junction_element} must have exactly one pinned git source"
            )
        source = git_sources[0]
        url, ref = source.get("url"), source.get("ref")
        if not isinstance(url, str) or not isinstance(ref, str):
            raise JunctionError(f"{junction_element} git source is not pinned")

        config = document.get("config", {})
        overrides = config.get("overrides", {}) if isinstance(config, dict) else {}
        if not isinstance(overrides, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in overrides.items()
        ):
            raise JunctionError(f"{junction_element} has invalid overrides")

        project = load_project(checkout, options, compose=True)
        self._junctions[junction_element] = Junction(
            element=junction_element,
            project=project,
            overrides=dict(overrides),
            source_url=url,
            source_ref=ref,
        )

    def compose_root(self) -> None:
        """Load root defaults after its external junction includes are resolvable."""
        try:
            config = load_composed(
                self.root.root / "project.conf",
                project_root=self.root.root,
                options=self.root.options,
                external_include=self.load_include,
            )
        except CompositionError as error:
            raise JunctionError(str(error)) from error
        if not isinstance(config, dict):
            raise JunctionError(f"{self.root.root}/project.conf must contain a mapping")
        variables = config.get("variables", {})
        environment = config.get("environment", {})
        if not isinstance(variables, dict) or not isinstance(environment, dict):
            raise JunctionError(
                f"{self.root.root}/project.conf has invalid variables or environment"
            )
        self.root = Project(
            name=self.root.name,
            root=self.root.root,
            element_path=self.root.element_path,
            options=self.root.options,
            variables=dict(variables),
            environment=dict(environment),
        )

    def resolve(self, owner: Project, dependency: str) -> ElementRef:
        if ":" not in dependency:
            return ElementRef(owner.name, _safe_relative(dependency, "dependency"))
        junction_name, element = dependency.split(":", 1)
        junction = self._junctions.get(junction_name)
        if junction is None:
            raise JunctionError(f"unresolved junction: {junction_name}")
        element = _safe_relative(element, "junction dependency")
        override = junction.overrides.get(element)
        if override is not None:
            return ElementRef(self.root.name, _safe_relative(override, "override"))
        return ElementRef(junction.project.name, element)

    def load_element(self, reference: ElementRef) -> dict[str, Any]:
        project = self.project(reference.project)
        path = project.root / project.element_path / reference.element
        try:
            value = load_composed(
                path,
                project_root=project.root,
                options=project.options,
                external_include=self.load_include,
            )
        except CompositionError as error:
            raise JunctionError(str(error)) from error
        if not isinstance(value, dict):
            raise JunctionError(f"{reference.qualified()} is not a mapping")
        value["variables"] = {
            **project.variables,
            **value.get("variables", {}),
        }
        value["environment"] = {
            **project.environment,
            **value.get("environment", {}),
        }
        return value

    def load_include(self, reference: str) -> Any:
        if ":" not in reference:
            raise JunctionError(f"external include is not qualified: {reference}")
        junction_name, include = reference.split(":", 1)
        junction = self._junctions.get(junction_name)
        if junction is None:
            raise JunctionError(f"unresolved junction include: {junction_name}")
        include = _safe_relative(include, "junction include")
        try:
            return load_composed(
                junction.project.root / include,
                project_root=junction.project.root,
                options=junction.project.options,
                external_include=self.load_include,
            )
        except CompositionError as error:
            raise JunctionError(str(error)) from error

    def project(self, name: str) -> Project:
        if name == self.root.name:
            return self.root
        for junction in self._junctions.values():
            if junction.project.name == name:
                return junction.project
        raise JunctionError(f"unknown project: {name}")

    def lock_metadata(self) -> dict[str, Any]:
        return {
            name: {
                "project": junction.project.name,
                "source": {
                    "url": junction.source_url,
                    "ref": junction.source_ref,
                },
                "overrides": dict(sorted(junction.overrides.items())),
                "options": dict(sorted(junction.project.options.items())),
            }
            for name, junction in sorted(self._junctions.items())
        }
