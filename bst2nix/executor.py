from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


class ExecutionError(RuntimeError):
    pass


_VARIABLE = re.compile(r"%\{([^}]+)\}")


def _merge(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ExecutionError(f"artifact is not a directory: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        symlinks=True,
        copy_function=shutil.copy2,
    )


def _location(root: Path, location: str) -> Path:
    value = PurePosixPath(location)
    if not value.is_absolute() or ".." in value.parts:
        raise ExecutionError(f"invalid dependency location: {location!r}")
    return root.joinpath(*value.parts[1:])


def _expand(command: str, variables: dict[str, str], element: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise ExecutionError(f"{element}: unresolved variable %{{{name}}}")
        return variables[name]

    return _VARIABLE.sub(replacement, command)


def execute_plan(
    plan: dict[str, Any],
    source: Path,
    dependencies: dict[str, Path],
    output: Path,
) -> None:
    source = source.resolve()
    output = output.resolve()
    dependencies = {name: path.resolve() for name, path in dependencies.items()}
    element = str(plan.get("element", "<unknown>"))
    expected = {item["element"] for item in plan.get("dependencies", [])}
    missing = sorted(expected - dependencies.keys())
    if missing:
        raise ExecutionError(f"{element}: missing dependencies: {', '.join(missing)}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="bst2nix-") as temporary:
        root = Path(temporary)
        build_root = root / "build"
        sysroot = root / "sysroot"
        build_root.mkdir()
        sysroot.mkdir()
        if source.is_dir():
            _merge(source, build_root)

        runtime = []
        locations: dict[str, Path] = {"/": sysroot}
        for dependency in plan.get("dependencies", []):
            artifact = dependencies[dependency["element"]]
            location = dependency.get("location", "/")
            destination = _location(root / "locations", location)
            if location == "/":
                destination = sysroot
            _merge(artifact, destination)
            locations[location] = destination
            if dependency.get("scope") in {"run", "all"}:
                runtime.append(artifact)

        variables = {
            **{key: str(value) for key, value in plan.get("variables", {}).items()},
            "build-root": str(build_root),
            "install-root": str(output),
            "sysroot": str(sysroot),
        }
        # BuildStream script dependencies are visible at configured absolute
        # locations. Map those paths into the private execution root without
        # requiring a privileged chroot.
        location_names = sorted(
            (name for name in locations if name != "/"), key=len, reverse=True
        )
        environment = {
            **os.environ,
            "BST2NIX_BUILD_ROOT": str(build_root),
            "BST2NIX_INSTALL_ROOT": str(output),
            "BST2NIX_SYSROOT": str(sysroot),
        }
        for entry in plan.get("commands", []):
            command = _expand(entry["command"], variables, element)
            for name in location_names:
                command = command.replace(name, str(locations[name]))
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", command],
                cwd=build_root,
                env=environment,
            )
            if result.returncode:
                raise ExecutionError(
                    f"{element}: {entry.get('phase', 'command')} failed "
                    f"with exit code {result.returncode}"
                )

        if not plan.get("commands"):
            for dependency in plan.get("dependencies", []):
                if dependency.get("scope") in {"run", "all"}:
                    _merge(dependencies[dependency["element"]], output)
        else:
            for artifact in runtime:
                _merge(artifact, output)
