from pathlib import Path

import pytest

from bst2nix.junction import ElementRef, JunctionError, JunctionResolver, load_project


def _project(root: Path, name: str) -> None:
    (root / "elements").mkdir(parents=True)
    (root / "project.conf").write_text(
        f"name: {name}\nelement-path: elements\n", encoding="utf-8"
    )


def test_resolves_junction_and_applies_override(tmp_path):
    root = tmp_path / "root"
    sdk = tmp_path / "sdk"
    _project(root, "gnome")
    _project(sdk, "freedesktop-sdk")
    (root / "elements" / "sdk.bst").write_text(
        """\
kind: junction
sources:
  - kind: git_repo
    url: example:sdk.git
    ref: 0123456789abcdef
config:
  overrides:
    components/glib.bst: sdk/glib.bst
""",
        encoding="utf-8",
    )

    resolver = JunctionResolver(load_project(root, {"arch": "x86_64"}))
    resolver.add("sdk.bst", sdk, {"target_arch": "x86_64"})

    assert resolver.resolve(
        resolver.root, "sdk.bst:components/systemd.bst"
    ) == ElementRef("freedesktop-sdk", "components/systemd.bst")
    assert resolver.resolve(
        resolver.root, "sdk.bst:components/glib.bst"
    ) == ElementRef("gnome", "sdk/glib.bst")
    assert resolver.lock_metadata()["sdk.bst"]["source"]["ref"] == "0123456789abcdef"


def test_rejects_unpinned_junction(tmp_path):
    root = tmp_path / "root"
    sdk = tmp_path / "sdk"
    _project(root, "root")
    _project(sdk, "sdk")
    (root / "elements" / "sdk.bst").write_text(
        "kind: junction\nsources:\n  - kind: git_repo\n    url: example:sdk\n",
        encoding="utf-8",
    )
    resolver = JunctionResolver(load_project(root, {}))
    with pytest.raises(JunctionError, match="not pinned"):
        resolver.add("sdk.bst", sdk, {})
