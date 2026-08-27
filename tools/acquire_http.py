#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import os
import random
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


def safe_name(value):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"unsafe archive path: {value}")
    return path


def safe_tar_member(member, _destination):
    safe_name(member.name)
    if member.isdev():
        raise SystemExit("archive contains a device")
    if member.islnk():
        safe_name(member.linkname)
    # Absolute symbolic links are valid package contents (for example,
    # autotools INSTALL links into /usr/share). Extracting a symlink does not
    # dereference its target, so retain it while still rejecting unsafe member
    # and hard-link paths.
    return member


def download(url, attempts=7):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "bst2nix/0.1"})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(min(60, 2 ** attempt) + random.uniform(0, 1))


def extract(data, kind, destination, filename):
    if kind in {"tar", "archive"}:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            archive.extractall(destination, filter=safe_tar_member)
    elif kind == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                safe_name(member.filename)
            archive.extractall(destination)
    else:
        name = filename or "source"
        target = destination.joinpath(*safe_name(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def deterministic_tar(source, output):
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            name = path.relative_to(source).as_posix()
            info = archive.gettarinfo(str(path), name)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 1
            if path.is_file():
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--kind", choices=["tar", "zip", "remote", "archive"], required=True)
    parser.add_argument("--filename")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = download(args.url)
    actual = hashlib.sha256(data).hexdigest()
    if actual != args.sha256:
        raise SystemExit(f"SHA-256 mismatch: expected {args.sha256}, got {actual}")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        tree = Path(temporary) / "tree"
        tree.mkdir()
        extract(data, args.kind, tree, args.filename)
        deterministic_tar(tree, args.output / "source.tar")
    (args.output / "source.json").write_text(json.dumps({
        "url": args.url,
        "sha256": actual,
        "size": len(data),
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
