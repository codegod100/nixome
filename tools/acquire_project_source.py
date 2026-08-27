#!/usr/bin/env python3
import argparse
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


_GNOME_SNAKEOIL_KEYS = {
    "files/boot-keys/tpm2-pcr-public.pem":
        "files/boot-keys/snakeoil/SECURE_BOOT_TPM_PCR_KEY",
    "files/boot-keys/fstab-tpm2-pcr-public.pem":
        "files/boot-keys/snakeoil/SECURE_BOOT_FSTAB_TPM_PCR_KEY",
}
_GNOME_CONCATENATED_SOURCES = {
    "files/boot-keys/modules/linux-module-cert.crt": [
        "files/boot-keys/snakeoil/SECURE_BOOT_MODULES_CRT",
        "files/boot-keys/snakeoil/SECURE_BOOT_SYSEXT_CRT",
    ],
}
_GNOME_SNAKEOIL_FILES = {
    "files/boot-keys/MODULES.key":
        "files/boot-keys/snakeoil/SECURE_BOOT_MODULES_KEY",
    "files/boot-keys/VENDOR.crt":
        "files/boot-keys/snakeoil/SECURE_BOOT_VENDOR_CRT",
    "files/boot-keys/VENDOR.key":
        "files/boot-keys/snakeoil/SECURE_BOOT_VENDOR_KEY",
}
_GNOME_DISTRIBUTION_KEY = (
    "files/boot-keys/snakeoil/SECURE_BOOT_DISTRIBUTION_KEY"
)


def _generated_source(repository, revision, path):
    source_path = _GNOME_SNAKEOIL_FILES.get(path)
    if source_path is not None:
        return subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{revision}:{source_path}"]
        )
    private_path = _GNOME_SNAKEOIL_KEYS.get(path)
    if private_path is not None:
        private_key = subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{revision}:{private_path}"]
        )
        return subprocess.run(
            ["openssl", "pkey", "-pubout"],
            input=private_key,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
    inputs = _GNOME_CONCATENATED_SOURCES.get(path)
    if inputs is not None:
        return b"".join(
            subprocess.check_output(
                ["git", "-C", str(repository), "show", f"{revision}:{input_path}"]
            )
            for input_path in inputs
        )
    if path == "files/boot-keys/import-pubring.pgp":
        distribution_key = subprocess.check_output(
            [
                "git", "-C", str(repository), "show",
                f"{revision}:{_GNOME_DISTRIBUTION_KEY}",
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            home.chmod(0o700)
            subprocess.run(
                ["gpg", "--batch", "--homedir", str(home), "--import"],
                input=distribution_key,
                stdout=subprocess.DEVNULL,
                check=True,
            )
            return subprocess.check_output(
                ["gpg", "--batch", "--homedir", str(home), "--export"]
            )
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    relative = PurePosixPath(args.path)
    if relative.is_absolute() or ".." in relative.parts:
        parser.error("path must remain inside the project")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        repository = Path(temporary) / "repository"
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(
            ["git", "-C", str(repository), "remote", "add", "origin", args.url],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "fetch", "--depth=1", "origin", args.revision],
            check=True,
        )
        object_result = subprocess.run(
            [
                "git", "-C", str(repository), "cat-file", "-t",
                f"{args.revision}:{args.path}",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if object_result.returncode:
            data = _generated_source(repository, args.revision, args.path)
            if data is None:
                raise FileNotFoundError(
                    f"{args.path} does not exist at {args.revision}"
                )
            object_type = "blob"
        else:
            object_type = object_result.stdout.strip()
            data = subprocess.check_output(
                [
                    "git", "-C", str(repository), "show",
                    f"{args.revision}:{args.path}",
                ]
            ) if object_type == "blob" else None
        with tarfile.open(args.output / "source.tar", "w", format=tarfile.PAX_FORMAT) as archive:
            if data is not None:
                info = tarfile.TarInfo(relative.name)
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 1
                archive.addfile(info, io.BytesIO(data))
            else:
                raw = subprocess.check_output(
                    ["git", "-C", str(repository), "archive", args.revision, args.path]
                )
                with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as source:
                    for member in source.getmembers():
                        try:
                            member.name = str(
                                PurePosixPath(member.name).relative_to(relative)
                            )
                        except ValueError:
                            # git archive includes parent directory entries
                            # before the requested subtree.
                            continue
                        if member.name == ".":
                            continue
                        member.uid = member.gid = 0
                        member.uname = member.gname = ""
                        member.mtime = 1
                        stream = source.extractfile(member) if member.isfile() else None
                        archive.addfile(member, stream)


if __name__ == "__main__":
    main()
