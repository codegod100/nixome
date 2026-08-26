from __future__ import annotations

import json
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

    for _ in range(20):
        expanded = _VARIABLE.sub(replacement, command)
        if expanded == command:
            return expanded
        command = expanded
    raise ExecutionError(f"{element}: recursive variable expansion")


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

        plugin_variables = {}
        if plan.get("kind") == "makemaker":
            plugin_variables["configure"] = (
                'perl Makefile.PL PREFIX="%{prefix}" '
                'DESTDIR="%{install-root}"'
            )
        elif plan.get("kind") == "modulebuild":
            plugin_variables["configure"] = (
                'perl Build.PL --prefix "%{prefix}" '
                '--destdir "%{install-root}"'
            )
        variables = {
            "autogen": "autoreconf -fvi",
            "bindir": "/usr/bin",
            "build-args": "--wheel --no-isolation",
            "cargo-args": "--release --locked --offline",
            "command-subdir": ".",
            "conf-args": "",
            "datadir": "/usr/share",
            "dist-dir": "%{build-root}/dist",
            "indep-libdir": "/usr/lib",
            "libdir": "/usr/lib",
            "make-args": "",
            "make": "make",
            "make-install": "make pure_install",
            "mandir": "/usr/share/man",
            "perl-build": "./Build",
            "perl-build-install": "./Build install",
            "prefix": "/usr",
            "sysconfdir": "/etc",
            **plugin_variables,
            **{key: str(value) for key, value in plan.get("variables", {}).items()},
            "build-root": str(build_root),
            "install-root": str(output),
            "sysroot": str(sysroot),
        }
        runtime = []
        locations: dict[str, Path] = {"/": sysroot}
        for dependency in plan.get("dependencies", []):
            artifact = dependencies[dependency["element"]]
            location = _expand(
                dependency.get("location", "/"), variables, element
            )
            if not location.startswith("/"):
                raise ExecutionError(
                    f"{element}: dependency location is not absolute: {location!r}"
                )
            destination = _location(root / "locations", location)
            if location in {"/", str(sysroot)}:
                destination = sysroot
            _merge(artifact, destination)
            locations[location] = destination
            if dependency.get("scope") in {"run", "all"}:
                runtime.append(artifact)

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
        if plan.get("kind") == "import":
            import_config = plan["import"]
            source_name = _expand(import_config["source"], variables, element)
            target_name = _expand(import_config["target"], variables, element)
            source_path = _location(build_root, source_name)
            target_path = _location(output, target_name)
            if source_path.is_dir():
                _merge(source_path, target_path)
            elif source_path.is_file():
                target_path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path / source_path.name)
            else:
                raise ExecutionError(
                    f"{element}: import source does not exist: {source_name}"
                )

        if plan.get("kind") == "collect_manifest":
            manifest = plan["manifest"]
            manifest_name = _expand(manifest["path"], variables, element)
            manifest_path = _location(output, manifest_name)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest["data"], indent=2, sort_keys=True) + "\n"
            )

        if plan.get("kind") == "collect_initial_scripts":
            initial_scripts = plan["initialScripts"]
            scripts_name = _expand(initial_scripts["path"], variables, element)
            scripts_path = _location(output, scripts_name)
            scripts_path.mkdir(parents=True, exist_ok=True)
            for index, entry in enumerate(initial_scripts["scripts"], start=1):
                dependency_name = re.sub(
                    r"[^A-Za-z0-9]", "_", entry["element"]
                )
                script_path = scripts_path / f"{index:03}-{dependency_name}"
                script_path.write_text(
                    _expand(entry["script"], variables, element)
                )
                script_path.chmod(0o755)

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

        if not plan.get("commands") and plan.get("kind") not in {
            "import",
            "collect_manifest",
            "collect_initial_scripts",
        }:
            for dependency in plan.get("dependencies", []):
                if dependency.get("scope") in {"run", "all"}:
                    _merge(dependencies[dependency["element"]], output)
        else:
            for artifact in runtime:
                _merge(artifact, output)
