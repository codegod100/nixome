from bst2nix.build_plan import element_build_plan


def test_preserves_script_commands_and_dependency_locations():
    graph = {
        "elements": {
            "gnome:image.bst": {
                "kind": "script",
                "variables": {"go-arch": "amd64"},
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
