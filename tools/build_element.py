#!/usr/bin/env python3
import argparse
import json
import tempfile
from pathlib import Path

from bst2nix.executor import execute_plan
from bst2nix.staging import stage_element_sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source", nargs=2, action="append", default=[])
    parser.add_argument("--dependency", nargs=2, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    groups = {source_id: Path(group) for source_id, group in args.source}
    with tempfile.TemporaryDirectory() as temporary:
        materialized = Path(temporary) / "materialized"
        materialized.mkdir()
        for source_id, group in groups.items():
            acquired = group / source_id if (group / source_id).is_dir() else group
            (materialized / source_id).symlink_to(acquired, target_is_directory=True)
        staged = Path(temporary) / "source"
        source_ids = list(spec["sources"])
        stage_element_sources(
            {
                "elements": {spec["plan"]["element"]: source_ids},
                "sources": spec["sources"],
            },
            spec["plan"]["element"],
            [materialized],
            staged,
        )
        execute_plan(
            spec["plan"],
            staged,
            {name: Path(path) for name, path in args.dependency},
            args.output,
        )


if __name__ == "__main__":
    main()
