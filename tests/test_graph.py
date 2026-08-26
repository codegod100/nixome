from pathlib import Path

from bst2nix.graph import lock_graph
from bst2nix.junction import JunctionResolver, load_project


def _project(root: Path, name: str) -> None:
    (root / "elements").mkdir(parents=True)
    (root / "project.conf").write_text(
        f"name: {name}\nelement-path: elements\n", encoding="utf-8"
    )


def test_walks_combined_graph_and_preserves_scopes(tmp_path):
    root = tmp_path / "root"
    sdk = tmp_path / "sdk"
    _project(root, "gnome")
    _project(sdk, "sdk")
    (root / "elements" / "sdk.bst").write_text(
        """\
kind: junction
sources:
- kind: git_repo
  url: example:sdk
  ref: sdk-revision
config:
  overrides:
    components/glib.bst: glib.bst
""",
        encoding="utf-8",
    )
    (root / "elements" / "image.bst").write_text(
        """\
kind: script
build-depends:
- filename:
  - sdk.bst:components/compiler.bst
  config:
    location: /toolchain
depends:
- filename: sdk.bst:components/glib.bst
  type: run
""",
        encoding="utf-8",
    )
    (root / "elements" / "glib.bst").write_text(
        "kind: manual\n", encoding="utf-8"
    )
    (sdk / "elements" / "components").mkdir()
    (sdk / "elements" / "components" / "compiler.bst").write_text(
        "kind: manual\n", encoding="utf-8"
    )

    resolver = JunctionResolver(load_project(root, {"arch": "x86_64"}))
    resolver.add("sdk.bst", sdk, {"target_arch": "x86_64"})
    graph = lock_graph(
        resolver,
        "image.bst",
        project_revisions={"gnome": "gnome-rev", "sdk": "sdk-rev"},
    )

    image = graph["elements"]["gnome:image.bst"]
    assert image["dependencies"] == {
        "build": ["sdk:components/compiler.bst"],
        "run": ["gnome:glib.bst"],
        "all": [],
    }
    assert sorted(graph["elements"]) == [
        "gnome:glib.bst",
        "gnome:image.bst",
        "sdk:components/compiler.bst",
    ]
    assert graph["projects"]["sdk"]["revision"] == "sdk-rev"
