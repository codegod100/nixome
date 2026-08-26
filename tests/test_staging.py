import io
import tarfile

import pytest

from bst2nix.staging import StagingError, stage_element_sources


def materialize(group, source_id, name="README", content=b"source\n"):
    directory = group / source_id
    directory.mkdir(parents=True)
    with tarfile.open(directory / "source.tar", "w") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))


def test_stages_ordered_git_sources_in_declared_directories(tmp_path):
    first, second = "a" * 64, "b" * 64
    group = tmp_path / "materialized"
    materialize(group, first)
    materialize(group, second, "module.txt", b"module\n")
    source_lock = {
        "elements": {"project:target.bst": [first, second]},
        "sources": {
            first: {"fetcher": "git"},
            second: {"fetcher": "git", "path": "subprojects/module"},
        },
    }

    output = tmp_path / "output"
    stage_element_sources(source_lock, "project:target.bst", [group], output)

    assert (output / "README").read_bytes() == b"source\n"
    assert (output / "subprojects/module/module.txt").read_bytes() == b"module\n"


def test_rejects_archive_path_traversal(tmp_path):
    source_id = "a" * 64
    group = tmp_path / "materialized"
    materialize(group, source_id, "../escape")
    source_lock = {
        "elements": {"project:target.bst": [source_id]},
        "sources": {source_id: {"fetcher": "git"}},
    }

    with pytest.raises(StagingError, match="unsafe path"):
        stage_element_sources(
            source_lock, "project:target.bst", [group], tmp_path / "output"
        )
