from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .junction import ElementRef, JunctionError, JunctionResolver


class GraphError(Exception):
    pass


@dataclass(frozen=True)
class Dependency:
    reference: ElementRef
    scope: str
    config: tuple[tuple[str, Any], ...] = ()


def _dependencies(
    raw: Any, owner: ElementRef, default_scope: str
) -> list[tuple[str, str, dict[str, Any]]]:
    if isinstance(raw, str):
        return [(raw, default_scope, {})]
    if not isinstance(raw, dict):
        raise GraphError(f"{owner.qualified()}: malformed dependency {raw!r}")
    filenames = raw.get("filename")
    if isinstance(filenames, str):
        filenames = [filenames]
    if not isinstance(filenames, list) or not all(
        isinstance(filename, str) for filename in filenames
    ):
        raise GraphError(f"{owner.qualified()}: malformed dependency {raw!r}")
    scope = raw.get("type", default_scope)
    if scope not in {"build", "run", "all"}:
        raise GraphError(
            f"{owner.qualified()}: unsupported dependency type {scope!r}"
        )
    config = raw.get("config", {})
    if not isinstance(config, dict):
        raise GraphError(f"{owner.qualified()}: malformed dependency config {config!r}")
    return [(filename, scope, config) for filename in filenames]


def lock_graph(
    resolver: JunctionResolver,
    target: str,
    *,
    project_revisions: dict[str, str],
    project_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Walk a composed, junction-resolved graph into deterministic JSON data."""

    nodes: dict[str, dict[str, Any]] = {}
    visiting: list[ElementRef] = []

    def visit(reference: ElementRef) -> None:
        qualified = reference.qualified()
        if qualified in nodes:
            return
        if reference in visiting:
            start = visiting.index(reference)
            cycle = " -> ".join(
                item.qualified() for item in [*visiting[start:], reference]
            )
            raise GraphError(f"dependency cycle: {cycle}")
        visiting.append(reference)

        try:
            document = resolver.load_element(reference)
            project = resolver.project(reference.project)
        except JunctionError as error:
            raise GraphError(str(error)) from error

        dependencies: list[Dependency] = []
        groups = (
            ("depends", "all"),
            ("build-depends", "build"),
            ("runtime-depends", "run"),
        )
        for group, default_scope in groups:
            values = document.get(group, [])
            if not isinstance(values, list):
                raise GraphError(f"{qualified}: {group} must compose to a list")
            for raw in values:
                for dependency_name, scope, config in _dependencies(
                    raw, reference, default_scope
                ):
                    try:
                        dependency_ref = resolver.resolve(project, dependency_name)
                    except JunctionError as error:
                        raise GraphError(f"{qualified}: {error}") from error
                    dependencies.append(
                        Dependency(
                            dependency_ref,
                            scope,
                            tuple(sorted(config.items())),
                        )
                    )
                    visit(dependency_ref)

        sources = document.get("sources", [])
        if not isinstance(sources, list):
            raise GraphError(f"{qualified}: sources must compose to a list")
        normalized_sources = []
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("kind"), str):
                raise GraphError(f"{qualified}: malformed source {source!r}")
            normalized_sources.append(source)

        by_scope = {
            scope: sorted(
                {
                    dependency.reference.qualified()
                    for dependency in dependencies
                    if dependency.scope == scope
                }
            )
            for scope in ("build", "run", "all")
        }
        nodes[qualified] = {
            "project": reference.project,
            "element": reference.element,
            "kind": str(document.get("kind", "<missing>")),
            "dependencies": by_scope,
            "dependencyDetails": [
                {
                    "element": dependency.reference.qualified(),
                    "scope": dependency.scope,
                    "config": dict(dependency.config),
                }
                for dependency in sorted(
                    dependencies,
                    key=lambda item: (
                        item.reference.qualified(),
                        item.scope,
                        repr(item.config),
                    ),
                )
            ],
            "sources": normalized_sources,
            "variables": document.get("variables", {}),
            "config": document.get("config", {}),
            "public": document.get("public", {}),
        }
        visiting.pop()

    root = ElementRef(resolver.root.name, target)
    visit(root)

    projects = {}
    project_urls = project_urls or {}
    project_names = {node["project"] for node in nodes.values()}
    for name in sorted(project_names):
        project = resolver.project(name)
        revision = project_revisions.get(name)
        if not revision:
            raise GraphError(f"missing immutable revision for project {name}")
        repository = project_urls.get(name)
        if project_urls and not repository:
            raise GraphError(f"missing canonical repository URL for project {name}")
        projects[name] = {
            "revision": revision,
            "options": dict(sorted(project.options.items())),
            **({"url": repository} if repository else {}),
        }

    return {
        "formatVersion": 1,
        "target": root.qualified(),
        "projects": projects,
        "junctions": resolver.lock_metadata(),
        "elements": dict(sorted(nodes.items())),
    }
