from bst2nix.buck_generator import generate_buck_sources


def test_groups_git_sources_by_repository():
    git_id, second_git_id, archive_id = "a" * 64, "d" * 64, "b" * 64
    result = generate_buck_sources(
        {
            "sources": {
                archive_id: {
                    "fetcher": "tar",
                    "url": "https://example/a",
                    "sha256": "f" * 64,
                },
                git_id: {
                    "fetcher": "git",
                    "url": "https://example/repo.git",
                    "revision": "c" * 40,
                    "submodules": True,
                },
                second_git_id: {
                    "fetcher": "git",
                    "url": "https://example/repo.git",
                    "revision": "e" * 40,
                    "submodules": True,
                },
            }
        }
    )
    assert result.count("git_repo_acquire(") == 1
    assert f'"{git_id}": "{"c" * 40}"' in result
    assert f'"{second_git_id}": "{"e" * 40}"' in result
    assert f'name = "http-{archive_id}"' in result
    assert 'tool = "root//tools:acquire_http"' in result
    assert "submodules = True" in result
    assert "# Git sources: 2; repository actions: 1" in result
    assert 'name = "manifest"' in result
    assert 'groups = [' in result
    assert 'load("@root//buck2:git_acquire.bzl", "git_repo_acquire")' in result
    assert 'tool = "root//tools:acquire_git"' in result
