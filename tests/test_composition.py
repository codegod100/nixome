from pathlib import Path

import pytest

from bst2nix.composition import (
    CompositionError,
    evaluate_condition,
    load_composed,
)


def test_conditions_are_data_not_python_execution():
    options = {"arch": "x86_64", "toolbox": False}
    assert evaluate_condition('arch == "x86_64" and not toolbox', options)
    with pytest.raises(CompositionError):
        evaluate_condition('__import__("os").system("false")', options)


def test_include_and_condition(tmp_path: Path):
    (tmp_path / "base.yml").write_text(
        "variables:\n  common: yes\nitems: [base]\n", encoding="utf-8"
    )
    (tmp_path / "element.yml").write_text(
        """\
(@): base.yml
variables:
  local: value
(?):
  - arch == "x86_64":
      variables:
        triplet: x86_64-linux
""",
        encoding="utf-8",
    )
    result = load_composed(
        tmp_path / "element.yml",
        project_root=tmp_path,
        options={"arch": "x86_64"},
    )
    assert result["variables"] == {
        "common": True,
        "local": "value",
        "triplet": "x86_64-linux",
    }
    assert result["items"] == ["base"]


def test_include_cannot_escape_project(tmp_path: Path):
    (tmp_path / "element.yml").write_text("(@): ../secret.yml\n", encoding="utf-8")
    with pytest.raises(CompositionError, match="escapes project"):
        load_composed(
            tmp_path / "element.yml",
            project_root=tmp_path,
            options={},
        )
