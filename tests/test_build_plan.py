from bst2nix.build_plan import element_build_plan


def test_preserves_script_commands_and_dependency_locations():
    graph = {
        "elements": {
            "gnome:image.bst": {
                "kind": "script",
                "variables": {"go-arch": "amd64"},
                "environment": {"CFLAGS": "%{build_flags}"},
                "config": {"commands": ["build-oci --arch %{go-arch}"]},
                "dependencyDetails": [
                    {
                        "element": "gnome:filesystem.bst",
                        "scope": "build",
                        "config": {"location": "/layer"},
                    }
                ],
            }
        }
    }

    assert element_build_plan(graph, "gnome:image.bst") == {
        "formatVersion": 1,
        "element": "gnome:image.bst",
        "kind": "script",
        "variables": {"go-arch": "amd64"},
        "environment": {"CFLAGS": "%{build_flags}"},
        "dependencies": [
            {
                "element": "gnome:filesystem.bst",
                "scope": "build",
                "location": "/layer",
            }
        ],
        "commands": [
            {"phase": "commands", "command": "build-oci --arch %{go-arch}"}
        ],
        "compose": {},
    }


def test_creates_import_plan():
    graph = {
        "elements": {
            "p:config.bst": {
                "kind": "import",
                "config": {"source": "/", "target": "%{sysconfdir}/example"},
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
            }
        }
    }

    plan = element_build_plan(graph, "p:config.bst")

    assert plan["commands"] == []
    assert plan["import"] == {
        "source": "/",
        "target": "%{sysconfdir}/example",
    }


def test_collects_dependency_source_manifest():
    graph = {
        "elements": {
            "p:source.bst": {
                "kind": "manual",
                "config": {},
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
                "sources": [
                    {"kind": "git_repo", "url": "example:source", "ref": "abc"}
                ],
                "public": {"cpe": {"product": "source"}},
            },
            "p:manifest.bst": {
                "kind": "collect_manifest",
                "config": {"path": "/usr/manifest.json"},
                "variables": {},
                "dependencies": {"all": [], "build": ["p:source.bst"], "run": []},
            },
        }
    }

    plan = element_build_plan(graph, "p:manifest.bst")

    assert plan["manifest"]["path"] == "/usr/manifest.json"
    assert plan["manifest"]["data"]["modules"][0]["x-cpe"] == {
        "product": "source"
    }


def test_collects_initial_scripts_and_accepts_null_variables():
    graph = {
        "elements": {
            "p:service.bst": {
                "kind": "stack",
                "config": {},
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
                "public": {
                    "initial-script": {"script": "echo %{optional}\n"}
                },
            },
            "p:scripts.bst": {
                "kind": "collect_initial_scripts",
                "config": {"path": "/initial_scripts"},
                "variables": {"optional": None},
                "dependencies": {
                    "all": [],
                    "build": ["p:service.bst"],
                    "run": [],
                },
            },
        }
    }

    plan = element_build_plan(graph, "p:scripts.bst")

    assert plan["variables"]["optional"] == ""
    assert plan["initialScripts"] == {
        "path": "/initial_scripts",
        "scripts": [
            {"element": "p:service.bst", "script": "echo %{optional}\n"}
        ],
    }


def test_appends_to_inherited_make_commands():
    graph = {
        "elements": {
            "p:package.bst": {
                "kind": "make",
                "config": {
                    "install-commands": {"(>)": ["rm %{install-root}/lib/lib.a"]}
                },
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
            }
        }
    }

    plan = element_build_plan(graph, "p:package.bst")

    install = [
        entry["command"]
        for entry in plan["commands"]
        if entry["phase"] == "install-commands"
    ]
    assert install == [
        'make -j1 DESTDIR="%{install-root}" install %{make-args}',
        "rm %{install-root}/lib/lib.a",
    ]


def test_accepts_variable_dependency_location():
    graph = {
        "elements": {
            "p:target.bst": {
                "kind": "manual",
                "config": {},
                "variables": {"tools": "/cross"},
                "dependencyDetails": [
                    {
                        "element": "p:headers.bst",
                        "scope": "build",
                        "config": {"location": "%{tools}"},
                    }
                ],
            }
        }
    }

    assert element_build_plan(graph, "p:target.bst")["dependencies"][0][
        "location"
    ] == "%{tools}"


def test_pyproject_prepends_custom_build_command():
    graph = {
        "elements": {
            "p:python.bst": {
                "kind": "pyproject",
                "config": {"build-commands": {"(<)": ["prepare-source"]}},
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
            }
        }
    }

    commands = element_build_plan(graph, "p:python.bst")["commands"]

    assert commands[0] == {
        "phase": "build-commands",
        "command": "prepare-source",
    }
    assert commands[1]["command"].startswith('cd "%{command-subdir}"')


def test_makemaker_uses_plugin_commands():
    graph = {
        "elements": {
            "p:perl.bst": {
                "kind": "makemaker",
                "config": {},
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
            }
        }
    }

    commands = element_build_plan(graph, "p:perl.bst")["commands"]

    assert [entry["command"] for entry in commands] == [
        "%{configure}",
        "%{make}",
        "%{make-install}",
    ]


def test_cargo_and_modulebuild_defaults():
    elements = {}
    for name, kind in (("rust.bst", "cargo"), ("perl.bst", "modulebuild")):
        elements[f"p:{name}"] = {
            "kind": kind,
            "config": {},
            "variables": {},
            "dependencies": {"all": [], "build": [], "run": []},
        }
    graph = {"elements": elements}

    cargo = element_build_plan(graph, "p:rust.bst")
    modulebuild = element_build_plan(graph, "p:perl.bst")

    assert any("cargo build" in entry["command"] for entry in cargo["commands"])
    assert [entry["command"] for entry in modulebuild["commands"]] == [
        "%{configure}",
        "%{perl-build}",
        "%{perl-build-install}",
    ]
