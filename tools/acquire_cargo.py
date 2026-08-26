#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath


def registry(crate, destination):
    name, version = crate["name"], crate["version"]
    url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    request = urllib.request.Request(url, headers={"User-Agent": "bst2nix/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != crate["sha"]:
        raise SystemExit(f"crate {name}-{version} SHA-256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        prefix = PurePosixPath(f"{name}-{version}")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[:1] != prefix.parts:
                raise SystemExit(f"crate {name}-{version} has an unsafe path")
            member.name = str(path.relative_to(prefix))
            if member.name != ".":
                archive.extract(member, destination, filter="data")
    (destination / ".cargo-checksum.json").write_text(
        json.dumps({"files": {}, "package": crate["sha"]}, sort_keys=True)
    )


def git_crate(crate, destination):
    with tempfile.TemporaryDirectory() as temporary:
        repository = Path(temporary) / "repository"
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(
            ["git", "-C", str(repository), "remote", "add", "origin", crate["repo"]],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "fetch", "--depth=1", "origin", crate["commit"]],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "checkout", "--detach", crate["commit"]],
            check=True,
        )
        shutil.copytree(repository, destination, ignore=shutil.ignore_patterns(".git"))
    (destination / ".cargo-checksum.json").write_text(
        json.dumps({"files": {}, "package": None}, sort_keys=True)
    )


def deterministic_tar(source, output):
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            info = archive.gettarinfo(str(path), path.relative_to(source).as_posix())
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
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    vendor = PurePosixPath(spec["vendorDir"])
    if vendor.is_absolute() or ".." in vendor.parts:
        parser.error("vendor directory escapes the source root")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "source"
        root.joinpath(*vendor.parts).mkdir(parents=True)
        for crate in spec["crates"]:
            destination = root.joinpath(*vendor.parts, f"{crate['name']}-{crate['version']}")
            if crate["kind"] == "registry":
                destination.mkdir()
                registry(crate, destination)
            elif crate["kind"] == "git":
                git_crate(crate, destination)
            else:
                raise SystemExit(f"unsupported Cargo source kind: {crate['kind']}")
        cargo_config = root / ".cargo" / "config.toml"
        cargo_config.parent.mkdir()
        relative_vendor = vendor.as_posix()
        mappings = [
            "[source.crates-io]",
            'replace-with = "bst2nix-vendored"',
            "",
            "[source.bst2nix-vendored]",
            f'directory = "{relative_vendor}"',
        ]
        for repository in sorted({
            crate["repo"] for crate in spec["crates"] if crate["kind"] == "git"
        }):
            mappings.extend([
                "",
                f'[source."git+{repository}"]',
                'replace-with = "bst2nix-vendored"',
            ])
        cargo_config.write_text("\n".join(mappings) + "\n")
        deterministic_tar(root, args.output / "source.tar")


if __name__ == "__main__":
    main()
