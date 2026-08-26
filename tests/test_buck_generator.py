from bst2nix.buck_generator import generate_buck_sources


def test_generates_stable_git_targets_only():
    git_id, archive_id = "a" * 64, "b" * 64
    result = generate_buck_sources(
        {
            "sources": {
                archive_id: {"fetcher": "tar", "url": "https://example/a"},
                git_id: {
                    "fetcher": "git",
                    "url": "https://example/repo.git",
                    "revision": "c" * 40,
                    "submodules": True,
                },
            }
        }
    )
    assert f'name = "git-{git_id}"' in result
    assert archive_id not in result
    assert "submodules = True" in result
    assert "# Git targets: 1" in result
    assert 'name = "manifest"' in result
    assert f'"{git_id}": ":git-{git_id}"' in result
