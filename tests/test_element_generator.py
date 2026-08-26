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
