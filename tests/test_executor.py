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
