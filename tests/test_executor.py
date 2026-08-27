import json
from unittest.mock import patch

from bst2nix.executor import execute_plan


def test_executes_commands_with_sources_dependencies_and_variables(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "input").write_text("source\n")
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    (dependency / "runtime").write_text("dependency\n")
    output = tmp_path / "output"
    plan = {
        "element": "project:example.bst",
        "variables": {"message": "built"},
        "dependencies": [
            {"element": "project:runtime.bst", "scope": "run", "location": "/"}
        ],
        "commands": [
            {
                "phase": "install-commands",
                "command": (
                    "mkdir -p %{install-root}/bin; "
                    "cat input > %{install-root}/bin/result; "
                    "echo %{message} >> %{install-root}/bin/result"
                ),
            }
        ],
    }

    execute_plan(
        plan,
        source,
        {"project:runtime.bst": dependency},
        output,
    )

    assert (output / "bin/result").read_text() == "source\nbuilt\n"
    assert (output / "runtime").read_text() == "dependency\n"


def test_maps_script_dependency_locations_without_chroot(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    layer = tmp_path / "layer"
    layer.mkdir()
    (layer / "file").write_text("layer\n")
    output = tmp_path / "output"
    plan = {
        "element": "project:image.bst",
        "variables": {},
        "dependencies": [
            {"element": "project:layer.bst", "scope": "build", "location": "/layer"}
        ],
        "commands": [
            {
                "phase": "commands",
                "command": "cp /layer/file %{install-root}/result",
            }
        ],
    }

    execute_plan(plan, source, {"project:layer.bst": layer}, output)

    assert (output / "result").read_text() == "layer\n"


def test_exposes_staged_dependency_tools_on_path(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    dependency = tmp_path / "dependency"
    tool = dependency / "usr/bin/generated-tool"
    tool.parent.mkdir(parents=True)
    tool.write_text("#!/bin/sh\necho dependency-tool\n")
    tool.chmod(0o755)
    output = tmp_path / "output"
    plan = {
        "element": "project:uses-tool.bst",
        "kind": "manual",
        "variables": {},
        "dependencies": [
            {"element": "project:tools.bst", "scope": "build", "location": "/"}
        ],
        "commands": [
            {
                "phase": "build-commands",
                "command": "generated-tool > %{install-root}/result",
            }
        ],
    }

    with patch("bst2nix.executor.shutil.which", return_value=None):
        execute_plan(plan, source, {"project:tools.bst": dependency}, output)

    assert (output / "result").read_text() == "dependency-tool\n"


def test_compose_outputs_build_dependency_artifacts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    (dependency / "composed").write_text("artifact\n")
    output = tmp_path / "output"
    plan = {
        "element": "project:compose.bst",
        "kind": "compose",
        "variables": {},
        "dependencies": [
            {"element": "project:input.bst", "scope": "build", "location": "/"}
        ],
        "commands": [],
        "compose": {},
    }

    execute_plan(plan, source, {"project:input.bst": dependency}, output)

    assert (output / "composed").read_text() == "artifact\n"


def test_executes_import_element(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "preset.conf").write_text("enable\n")
    output = tmp_path / "output"
    plan = {
        "element": "project:preset.bst",
        "kind": "import",
        "variables": {},
        "dependencies": [],
        "commands": [],
        "import": {"source": "/", "target": "%{indep-libdir}/systemd"},
    }

    execute_plan(plan, source, {}, output)

    assert (output / "usr/lib/systemd/preset.conf").read_text() == "enable\n"


def test_executes_collect_manifest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    output = tmp_path / "output"
    plan = {
        "element": "project:manifest.bst",
        "kind": "collect_manifest",
        "variables": {},
        "dependencies": [
            {"element": "project:package.bst", "scope": "build", "location": "/"}
        ],
        "commands": [],
        "manifest": {
            "path": "/usr/manifest.json",
            "data": {"modules": [{"name": "project:package.bst"}]},
        },
    }

    execute_plan(plan, source, {"project:package.bst": dependency}, output)

    assert json.loads((output / "usr/manifest.json").read_text()) == {
        "modules": [{"name": "project:package.bst"}]
    }


def test_executes_collect_initial_scripts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    output = tmp_path / "output"
    plan = {
        "element": "project:scripts.bst",
        "kind": "collect_initial_scripts",
        "variables": {"message": "ready"},
        "dependencies": [
            {"element": "project:service.bst", "scope": "build", "location": "/"}
        ],
        "commands": [],
        "initialScripts": {
            "path": "/initial_scripts",
            "scripts": [
                {
                    "element": "project:service.bst",
                    "script": "#!/bin/sh\necho %{message}\n",
                }
            ],
        },
    }

    execute_plan(plan, source, {"project:service.bst": dependency}, output)

    script = output / "initial_scripts/001-project_service_bst"
    assert script.read_text() == "#!/bin/sh\necho ready\n"
    assert script.stat().st_mode & 0o777 == 0o755


def test_expands_nested_variables(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "output"
    plan = {
        "element": "project:variables.bst",
        "kind": "manual",
        "variables": {"destination": "%{bindir}/result"},
        "dependencies": [],
        "commands": [
            {
                "phase": "install-commands",
                "command": "mkdir -p %{install-root}%{bindir}; "
                "touch %{install-root}%{destination}",
            }
        ],
    }

    execute_plan(plan, source, {}, output)

    assert (output / "usr/bin/result").is_file()


def test_supplies_empty_optional_install_extension(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "output"
    plan = {
        "element": "project:optional-install.bst",
        "kind": "manual",
        "variables": {},
        "dependencies": [],
        "commands": [
            {
                "phase": "install-commands",
                "command": "touch %{install-root}/result\n%{install-extra}",
            }
        ],
    }

    execute_plan(plan, source, {}, output)

    assert (output / "result").is_file()


def test_autotools_uses_existing_configure_without_autoreconf(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    configure = source / "configure"
    configure.write_text("#!/bin/sh\nexit 0\n")
    configure.chmod(0o755)
    output = tmp_path / "output"
    plan = {
        "element": "project:configured.bst",
        "kind": "autotools",
        "variables": {},
        "dependencies": [],
        "commands": [
            {
                "phase": "configure-commands",
                "command": "%{autogen}",
            }
        ],
    }

    with patch("bst2nix.executor.shutil.which", return_value=None):
        execute_plan(plan, source, {}, output)


def test_expands_dependency_location(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    (dependency / "header").write_text("header\n")
    output = tmp_path / "output"
    plan = {
        "element": "project:cross.bst",
        "kind": "manual",
        "variables": {"tools": "/cross"},
        "dependencies": [
            {
                "element": "project:headers.bst",
                "scope": "build",
                "location": "%{tools}",
            }
        ],
        "commands": [
            {
                "phase": "install-commands",
                "command": "cp %{tools}/header %{install-root}/header",
            }
        ],
    }

    execute_plan(plan, source, {"project:headers.bst": dependency}, output)

    assert (output / "header").read_text() == "header\n"
