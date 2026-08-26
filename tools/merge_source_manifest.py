#!/usr/bin/env python3
import argparse, json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--source", nargs=2, action="append", default=[])
p.add_argument("--group", action="append", default=[])
p.add_argument("--output", required=True)
args = p.parse_args()
sources = {}

entries = list(args.source)
for group in args.group:
    entries.extend(
        (child.name, str(child))
        for child in Path(group).iterdir()
        if child.is_dir() and (child / "source.json").is_file()
    )

for source_id, directory in sorted(entries):
    metadata = json.loads((Path(directory) / "source.json").read_text())
    previous = sources.get(source_id)
    if previous is not None and previous != metadata:
        raise SystemExit(f"conflicting acquisition metadata for {source_id}")
    sources[source_id] = metadata
Path(args.output).write_text(
    json.dumps(
        {"formatVersion": 1, "sourceCount": len(sources), "sources": sources},
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
