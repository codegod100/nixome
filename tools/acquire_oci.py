#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath


ACCEPT = ", ".join([
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])

class AuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        redirected = super().redirect_request(
            request, fp, code, message, headers, new_url
        )
        if redirected is not None and request.has_header("Authorization"):
            if urllib.parse.urlparse(request.full_url).netloc == urllib.parse.urlparse(new_url).netloc:
                redirected.add_unredirected_header(
                    "Authorization", request.get_header("Authorization")
                )
            else:
                redirected.remove_header("Authorization")
        return redirected


OPENER = urllib.request.build_opener(AuthRedirectHandler())


def request(url, headers=None):
    req = urllib.request.Request(url, headers={"Accept": ACCEPT, **(headers or {})})
    try:
        return OPENER.open(req, timeout=120).read()
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
        challenge = error.headers.get("WWW-Authenticate", "")
        match = re.match(r'Bearer\s+realm="([^"]+)"(?:,service="([^"]+)")?(?:,scope="([^"]+)")?', challenge)
        if not match:
            raise
        realm, service, scope = match.groups()
        query = {key: value for key, value in (("service", service), ("scope", scope)) if value}
        token_data = json.loads(
            urllib.request.urlopen(realm + "?" + urllib.parse.urlencode(query), timeout=120).read()
        )
        token = token_data.get("token") or token_data["access_token"]
        authenticated = urllib.request.Request(
            url, headers={"Accept": ACCEPT, "Authorization": f"Bearer {token}", **(headers or {})}
        )
        return OPENER.open(authenticated, timeout=120).read()


def safe_members(archive):
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.isdev():
            raise SystemExit(f"unsafe OCI layer entry: {member.name}")
        yield member


def apply_layer(data, root):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        members = list(safe_members(archive))
        for member in members:
            path = PurePosixPath(member.name)
            if path.name == ".wh..wh..opq":
                directory = root.joinpath(*path.parent.parts)
                if directory.exists():
                    for child in directory.iterdir():
                        if child.name != path.name:
                            shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
            elif path.name.startswith(".wh."):
                target = root.joinpath(*path.parent.parts, path.name[4:])
                if target.exists() or target.is_symlink():
                    shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
        archive.extractall(
            root,
            members=[member for member in members if not PurePosixPath(member.name).name.startswith(".wh.")],
            filter="data",
        )


def deterministic_tar(root, output):
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            info = archive.gettarinfo(str(path), path.relative_to(root).as_posix())
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
    parser.add_argument("--digest", required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.url)
    repository = parsed.path.strip("/")
    api = f"{parsed.scheme}://{parsed.netloc}/v2/{repository}"
    digest = f"sha256:{args.digest}"
    manifest_data = request(f"{api}/manifests/{digest}")
    if hashlib.sha256(manifest_data).hexdigest() != args.digest:
        raise SystemExit("OCI manifest digest mismatch")
    manifest = json.loads(manifest_data)
    config_descriptor = manifest["config"]
    config_data = request(f"{api}/blobs/{config_descriptor['digest']}")
    if "sha256:" + hashlib.sha256(config_data).hexdigest() != config_descriptor["digest"]:
        raise SystemExit("OCI config digest mismatch")
    config = json.loads(config_data)
    if config.get("architecture") != args.architecture:
        raise SystemExit(
            f"OCI architecture mismatch: expected {args.architecture}, got {config.get('architecture')}"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "rootfs"
        root.mkdir()
        for descriptor in manifest["layers"]:
            data = request(f"{api}/blobs/{descriptor['digest']}")
            if "sha256:" + hashlib.sha256(data).hexdigest() != descriptor["digest"]:
                raise SystemExit(f"OCI layer digest mismatch: {descriptor['digest']}")
            apply_layer(data, root)
        deterministic_tar(root, args.output / "source.tar")
    (args.output / "source.json").write_text(json.dumps({
        "url": args.url,
        "digest": digest,
        "architecture": args.architecture,
        "layers": len(manifest["layers"]),
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
