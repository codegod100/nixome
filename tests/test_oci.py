import hashlib
import json
import tarfile

from bst2nix.oci import export_oci


def test_exports_deterministic_oci_layout(tmp_path):
    rootfs = tmp_path / "rootfs"
    (rootfs / "usr/bin").mkdir(parents=True)
    (rootfs / "usr/bin/gnome-shell").write_text("shell\n")
    first, second = tmp_path / "first", tmp_path / "second"

    export_oci(rootfs, first, reference="gnomeos:test")
    export_oci(rootfs, second, reference="gnomeos:test")

    first_files = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    index = json.loads((first / "index.json").read_text())
    manifest_descriptor = index["manifests"][0]
    assert manifest_descriptor["annotations"]["org.opencontainers.image.ref.name"] == "gnomeos:test"
    manifest_digest = manifest_descriptor["digest"].removeprefix("sha256:")
    manifest_data = (first / "blobs/sha256" / manifest_digest).read_bytes()
    assert hashlib.sha256(manifest_data).hexdigest() == manifest_digest
    manifest = json.loads(manifest_data)
    layer_digest = manifest["layers"][0]["digest"].removeprefix("sha256:")
    with tarfile.open(first / "blobs/sha256" / layer_digest) as layer:
        assert layer.extractfile("usr/bin/gnome-shell").read() == b"shell\n"
