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
    elif kind in {"manual", "autotools", "meson", "cmake", "make"}:
        command_groups = [(key, config.get(key, [])) for key in _COMMAND_KEYS]
    elif kind in {"compose", "filter", "stack", "junction", "import"}:
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
        config = detail.get("config", {})
        location = config.get("location", "/")
        if not isinstance(location, str) or not location.startswith("/"):
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
        isinstance(key, str) and isinstance(value, (str, int, bool))
        for key, value in variables.items()
    ):
        raise BuildPlanError(f"{name}: variables must contain scalar values")
    return {
        "formatVersion": 1,
        "element": name,
        "kind": kind,
        "variables": {key: str(value) for key, value in sorted(variables.items())},
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
