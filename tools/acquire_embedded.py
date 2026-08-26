#!/usr/bin/env python3
import argparse
import base64
import binascii
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--encoding", choices=["base64"], required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--filename", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    filename = PurePosixPath(args.filename)
    if filename.is_absolute() or ".." in filename.parts:
        parser.error("filename must remain inside the source root")
    try:
        content = base64.b64decode(args.data, validate=True)
    except binascii.Error as error:
        parser.error(f"invalid base64 source: {error}")
    args.output.mkdir(parents=True, exist_ok=True)
    archive_path = args.output / "source.tar"
    with tarfile.open(archive_path, "w", format=tarfile.PAX_FORMAT) as archive:
        info = tarfile.TarInfo(filename.as_posix())
        info.size = len(content)
        info.mode = 0o644
        info.uid = info.gid = 0
        info.mtime = 1
        import io
        archive.addfile(info, io.BytesIO(content))
    (args.output / "source.json").write_text(json.dumps({
        "encoding": args.encoding,
        "filename": filename.as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
