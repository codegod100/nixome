#!/usr/bin/env python3
import argparse, json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--source", nargs=2, action="append", default=[])
p.add_argument("--output", required=True)
args = p.parse_args()
sources = {}
for source_id, directory in sorted(args.source):
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
