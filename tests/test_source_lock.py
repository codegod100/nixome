import pytest

from bst2nix.source_lock import SourceLockError, lock_sources, normalize_source


def test_normalizes_git_describe_and_archive():
    aliases = {"git": "https://example/", "files": "https://files/"}
    assert normalize_source(
        {
            "kind": "git_repo",
            "url": "git:project.git",
            "ref": "v1.0-2-g0123456789abcdef",
        },
        project="test",
        aliases=aliases,
    )["revision"] == "0123456789abcdef"
    assert normalize_source(
        {
            "kind": "tar",
            "url": "files:archive.tar.xz",
            "ref": "a" * 64,
        },
        project="test",
        aliases=aliases,
    )["sha256"] == "a" * 64


def test_rejects_mutable_git_ref():
    with pytest.raises(SourceLockError, match="does not contain a commit"):
        normalize_source(
            {"kind": "git_repo", "url": "git:x", "ref": "main"},
            project="test",
            aliases={"git": "https://example/"},
        )


def test_deduplicates_normalized_sources():
    source = {"kind": "remote", "url": "files:x", "ref": "b" * 64}
    graph = {
        "target": "p:a.bst",
        "elements": {
            "p:a.bst": {"project": "p", "sources": [source]},
            "p:b.bst": {"project": "p", "sources": [source]},
        },
    }
    result = lock_sources(graph, {"p": {"files": "https://example/"}})
    assert result["declarationCount"] == 2
    assert result["uniqueSourceCount"] == 1
