from __future__ import annotations

from typing import Any


class BuildPlanError(ValueError):
    pass


_COMMAND_KEYS = (
    "configure-commands",
    "build-commands",
    "install-commands",
    "strip-commands",
)

_DEFAULT_COMMANDS = {
    "make": {
        "configure-commands": [],
        "build-commands": ["make %{make-args}"],
        "install-commands": [
            'make -j1 DESTDIR="%{install-root}" install %{make-args}'
        ],
        "strip-commands": [],
    },
    "autotools": {
        "configure-commands": [
            "%{autogen}",
            './configure --prefix="%{prefix}" %{conf-args}',
        ],
        "build-commands": ["make %{make-args}"],
        "install-commands": [
            'make -j1 DESTDIR="%{install-root}" install %{make-args}'
        ],
        "strip-commands": [],
    },
    "makemaker": {
        "configure-commands": ["%{configure}"],
        "build-commands": ["%{make}"],
        "install-commands": ["%{make-install}"],
        "strip-commands": [],
    },
    "pyproject": {
        "configure-commands": [],
        "build-commands": [
            'cd "%{command-subdir}" && '
            '%{python} -m build %{build-args} --outdir "%{dist-dir}"'
        ],
        "install-commands": [
            'for wheel in "%{dist-dir}"/*.whl; do '
            '%{python} -m installer "$wheel" --destdir "%{install-root}"; '
            "done"
        ],
        "strip-commands": [],
    },
    "modulebuild": {
        "configure-commands": ["%{configure}"],
        "build-commands": ["%{perl-build}"],
        "install-commands": ["%{perl-build-install}"],
        "strip-commands": [],
    },
    "cargo": {
        "configure-commands": [],
        "build-commands": [
            'cd "%{command-subdir}" && cargo build %{cargo-args}'
        ],
        "install-commands": [
            'cd "%{command-subdir}" && cargo install '
            '--path . --root "%{install-root}%{prefix}" %{cargo-args}'
        ],
        "strip-commands": [],
    },
}


def _phase_commands(kind: str, config: dict[str, Any], key: str) -> Any:
    defaults = _DEFAULT_COMMANDS.get(kind, {}).get(key, [])
    value = config.get(key, defaults)
    if value is None:
        return defaults
    if isinstance(value, dict) and set(value) == {"(>)"}:
        extension = value["(>)"]
        return [*defaults, *extension] if isinstance(extension, list) else value
    if isinstance(value, dict) and set(value) == {"(<)"}:
        prepend = value["(<)"]
        return [*prepend, *defaults] if isinstance(prepend, list) else value
    return value


def element_build_plan(graph: dict[str, Any], name: str) -> dict[str, Any]:
    element = graph.get("elements", {}).get(name)
    if not isinstance(element, dict):
        raise BuildPlanError(f"unknown element: {name}")
    kind = element.get("kind")
    config = element.get("config", {})
    if not isinstance(config, dict):
        raise BuildPlanError(f"{name}: element config is not a mapping")
    if kind == "script":
        command_groups = [("commands", config.get("commands", []))]
    elif kind in {
        "manual", "autotools", "meson", "cmake", "make",
        "makemaker", "pyproject", "modulebuild", "cargo",
    }:
        command_groups = [
            (key, _phase_commands(kind, config, key)) for key in _COMMAND_KEYS
        ]
    elif kind in {
        "compose", "filter", "stack", "junction", "import", "collect_manifest",
        "collect_initial_scripts",
    }:
        command_groups = []
    else:
        raise BuildPlanError(f"{name}: unsupported element kind {kind!r}")

    commands = []
    for phase, values in command_groups:
        if not isinstance(values, list) or not all(
            isinstance(command, str) for command in values
        ):
            raise BuildPlanError(f"{name}: {phase} must be a list of commands")
        commands.extend({"phase": phase, "command": command} for command in values)

    details = element.get("dependencyDetails")
    if details is None:
        details = [
            {"element": dependency, "scope": scope, "config": {}}
            for scope, dependencies in element.get("dependencies", {}).items()
            for dependency in dependencies
        ]
    dependencies = []
    for detail in details:
        dependency_config = detail.get("config", {})
        location = dependency_config.get("location", "/")
        if not isinstance(location, str) or not (
            location.startswith("/") or location.startswith("%{")
        ):
            raise BuildPlanError(
                f"{name}: dependency {detail.get('element')} has invalid location"
            )
        dependencies.append({
            "element": detail["element"],
            "scope": detail["scope"],
            "location": location,
        })

    variables = element.get("variables", {})
    if not isinstance(variables, dict) or not all(
        isinstance(key, str) and (
            value is None or isinstance(value, (str, int, bool))
        )
        for key, value in variables.items()
    ):
        raise BuildPlanError(f"{name}: variables must contain scalar values")
    plan = {
        "formatVersion": 1,
        "element": name,
        "kind": kind,
        "variables": {
            key: "" if value is None else str(value)
            for key, value in sorted(variables.items())
        },
        "dependencies": dependencies,
        "commands": commands,
        "compose": {
            key: config[key]
            for key in ("include", "exclude", "integrate")
            if key in config
        },
        **(
            {
                "import": {
                    "source": config.get("source", "/"),
                    "target": config.get("target", "/"),
                }
            }
            if kind == "import"
            else {}
        ),
    }
    if kind == "collect_manifest":
        visited = set()
        modules = []

        def collect(dependency_name: str) -> None:
            if dependency_name in visited:
                return
            visited.add(dependency_name)
            dependency = graph["elements"][dependency_name]
            for values in dependency.get("dependencies", {}).values():
                for child in values:
                    collect(child)
            source_entries = []
            for source in dependency.get("sources", []):
                source_kind = source.get("kind")
                if source_kind in {"git_repo", "git_module"}:
                    source_entries.append({
                        "type": "git",
                        "url": source.get("url"),
                        "commit": source.get("ref"),
                    })
                elif source_kind in {"tar", "zip", "remote"}:
                    source_entries.append({
                        "type": "archive",
                        "url": source.get("url"),
                        "sha256": source.get("ref"),
                    })
                elif source_kind in {"patch", "patch_queue"}:
                    source_entries.append({
                        "type": "patch",
                        "path": source.get("path"),
                    })
            if source_entries:
                module = {
                    "name": dependency_name,
                    "sources": source_entries,
                }
                public = dependency.get("public", {})
                if isinstance(public, dict) and isinstance(public.get("cpe"), dict):
                    module["x-cpe"] = public["cpe"]
                modules.append(module)

        for dependency in plan["dependencies"]:
            collect(dependency["element"])
        plan["manifest"] = {
            "path": config.get("path", "/manifest.json"),
            "data": {"modules": modules},
        }
    if kind == "collect_initial_scripts":
        scripts = []
        for dependency in plan["dependencies"]:
            public = graph["elements"][dependency["element"]].get("public", {})
            initial_script = (
                public.get("initial-script", {}) if isinstance(public, dict) else {}
            )
            script = (
                initial_script.get("script")
                if isinstance(initial_script, dict)
                else None
            )
            if script is not None:
                if not isinstance(script, str):
                    raise BuildPlanError(
                        f"{name}: {dependency['element']} initial script "
                        "must be a string"
                    )
                scripts.append({
                    "element": dependency["element"],
                    "script": script,
                })
        path = config.get("path")
        if not isinstance(path, str):
            raise BuildPlanError(f"{name}: initial scripts path must be a string")
        plan["initialScripts"] = {"path": path, "scripts": scripts}
    return plan
