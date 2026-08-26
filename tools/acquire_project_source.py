#!/usr/bin/env python3
import argparse
import io
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


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
        object_type = subprocess.check_output(
            ["git", "-C", str(repository), "cat-file", "-t", f"{args.revision}:{args.path}"],
            text=True,
        ).strip()
        data = subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{args.revision}:{args.path}"]
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
