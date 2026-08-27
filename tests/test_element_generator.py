from bst2nix.element_generator import generate_buck_elements


def test_generates_dependency_ordered_element_targets():
    source_id = "a" * 64
    graph = {
        "target": "p:image.bst",
        "elements": {
            "p:base.bst": {
                "kind": "manual",
                "config": {},
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
            },
            "p:image.bst": {
                "kind": "script",
                "config": {"commands": []},
                "variables": {},
                "dependencies": {
                    "all": ["p:base.bst"],
                    "build": [],
                    "run": [],
                },
            },
        },
    }
    lock = {
        "elements": {"p:base.bst": [source_id], "p:image.bst": []},
        "sources": {
            source_id: {
                "fetcher": "git",
                "url": "https://example/repo.git",
                "revision": "b" * 40,
            }
        },
    }

    result = generate_buck_elements(graph, lock)

    assert "# Executable elements: 2; blocked elements: 0" in result
    assert result.count("element_execute(") == 2
    assert 'name = "target"' in result


def test_renders_starlark_boolean_source_attributes():
    graph = {
        "target": "p:source.bst",
        "elements": {
            "p:source.bst": {
                "kind": "manual",
                "config": {},
                "variables": {},
                "dependencies": {"all": [], "build": [], "run": []},
            }
        },
    }
    source_lock = {
        "elements": {"p:source.bst": ["source"]},
        "sources": {
            "source": {
                "fetcher": "git",
                "url": "https://example.test/source.git",
                "revision": "abc",
                "submodules": False,
                "directory": 4.4,
            }
        },
    }

    result = generate_buck_elements(graph, source_lock)

    assert '"submodules": False' in result
    assert '"submodules": false' not in result
    assert '"directory": "4.4"' in result
    assert '"sourceOrder": ["source"]' in result
