from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from typing import Any


class OciError(ValueError):
    pass


def _json_blob(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_blob(blobs: Path, data: bytes) -> dict[str, Any]:
    digest = _digest(data)
    (blobs / digest).write_bytes(data)
    return {
        "digest": f"sha256:{digest}",
        "size": len(data),
    }


def _layer(rootfs: Path, destination: Path) -> bytes:
    with tarfile.open(destination, "w", format=tarfile.PAX_FORMAT) as archive:
        paths = sorted(rootfs.rglob("*"), key=lambda path: path.relative_to(rootfs).as_posix())
        for path in paths:
            relative = path.relative_to(rootfs).as_posix()
            info = archive.gettarinfo(str(path), relative)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 1
            if path.is_file():
                with path.open("rb") as source:
                    archive.addfile(info, source)
            else:
                archive.addfile(info)
    return destination.read_bytes()


def export_oci(
    rootfs: Path,
    output: Path,
    *,
    architecture: str = "amd64",
    reference: str = "gnomeos:latest",
    labels: dict[str, str] | None = None,
) -> None:
    if not rootfs.is_dir():
        raise OciError(f"root filesystem is not a directory: {rootfs}")
    if architecture not in {"amd64", "arm64"}:
        raise OciError(f"unsupported OCI architecture: {architecture}")
    if output.exists():
        shutil.rmtree(output)
    blobs = output / "blobs" / "sha256"
    blobs.mkdir(parents=True)

    layer_path = output / ".layer.tar"
    layer = _layer(rootfs, layer_path)
    layer_path.unlink()
    layer_descriptor = _write_blob(blobs, layer) | {
        "mediaType": "application/vnd.oci.image.layer.v1.tar"
    }
    config = _json_blob({
        "architecture": architecture,
        "config": {"Labels": dict(sorted((labels or {}).items()))},
        "created": "1970-01-01T00:00:01Z",
        "history": [{"created": "1970-01-01T00:00:01Z", "created_by": "bst2nix"}],
        "os": "linux",
        "rootfs": {
            "diff_ids": [f"sha256:{_digest(layer)}"],
            "type": "layers",
        },
    })
    config_descriptor = _write_blob(blobs, config) | {
        "mediaType": "application/vnd.oci.image.config.v1+json"
    }
    manifest = _json_blob({
        "config": config_descriptor,
        "layers": [layer_descriptor],
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "schemaVersion": 2,
    })
    manifest_descriptor = _write_blob(blobs, manifest) | {
        "annotations": {"org.opencontainers.image.ref.name": reference},
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
    }
    (output / "index.json").write_bytes(_json_blob({
        "manifests": [manifest_descriptor],
        "schemaVersion": 2,
    }))
    (output / "oci-layout").write_bytes(
        _json_blob({"imageLayoutVersion": "1.0.0"})
    )
