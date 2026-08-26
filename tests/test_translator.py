import json
from pathlib import Path

import pytest

from bst2nix.translator import TranslationError, translate


EXAMPLE = Path(__file__).parents[1] / "examples" / "hello"


def test_example_matches_checked_in_graph():
    expected = json.loads((EXAMPLE / "graph.json").read_text(encoding="utf-8"))
    assert translate(EXAMPLE, "hello.bst") == expected


def test_rejects_path_escape(tmp_path):
    (tmp_path / "project.conf").write_text(
        "name: unsafe\nelement-path: ../elements\n", encoding="utf-8"
    )
    with pytest.raises(TranslationError, match="must stay within"):
        translate(tmp_path, "hello.bst")


def test_rejects_unsupported_kind(tmp_path):
    (tmp_path / "elements").mkdir()
    (tmp_path / "project.conf").write_text("name: test\n", encoding="utf-8")
    (tmp_path / "elements" / "hello.bst").write_text(
        "kind: meson\n", encoding="utf-8"
    )
    with pytest.raises(TranslationError, match="unsupported kind"):
        translate(tmp_path, "hello.bst")


def test_reports_dependency_cycle(tmp_path):
    (tmp_path / "elements").mkdir()
    (tmp_path / "project.conf").write_text("name: cycle\n", encoding="utf-8")
    (tmp_path / "elements" / "a.bst").write_text(
        "kind: manual\ndepends: [b.bst]\n", encoding="utf-8"
    )
    (tmp_path / "elements" / "b.bst").write_text(
        "kind: manual\ndepends: [a.bst]\n", encoding="utf-8"
    )
    with pytest.raises(TranslationError, match="a.bst -> b.bst -> a.bst"):
        translate(tmp_path, "a.bst")
