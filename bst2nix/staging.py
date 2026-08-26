from __future__ import annotations

import shutil
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any


class StagingError(ValueError):
    pass


def _destination(root: Path, value: Any, source_id: str) -> Path:
    if value in (None, "", "."):
        return root
    if not isinstance(value, str):
        raise StagingError(f"source {source_id} has an invalid staging directory")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise StagingError(f"source {source_id} staging directory escapes the root")
    return root.joinpath(*relative.parts)


def _safe_members(archive: tarfile.TarFile, source_id: str):
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise StagingError(f"source {source_id} archive contains an unsafe path")
        if member.isdev():
            raise StagingError(f"source {source_id} archive contains a device")
        yield member


def _materialized_sources(groups: list[Path]) -> dict[str, Path]:
    result = {}
    for group in groups:
        for child in group.iterdir():
            if child.is_dir() and (child / "source.tar").is_file():
                previous = result.setdefault(child.name, child / "source.tar")
                if previous != child / "source.tar":
                    raise StagingError(f"duplicate materialization for source {child.name}")
    return result


def stage_element_sources(
    source_lock: dict[str, Any],
    element: str,
    materialized_groups: list[Path],
    output: Path,
) -> None:
    declarations = source_lock.get("elements", {}).get(element)
    if declarations is None:
        raise StagingError(f"unknown element: {element}")
    sources = source_lock.get("sources", {})
    materialized = _materialized_sources(materialized_groups)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for source_id in declarations:
        source = sources.get(source_id)
        if not isinstance(source, dict):
            raise StagingError(f"missing lock entry for source {source_id}")
        if source.get("fetcher") not in {"git", "tar", "zip", "remote", "archive"}:
            raise StagingError(
                f"source {source_id} uses unsupported staging fetcher "
                f"{source.get('fetcher')!r}"
            )
        archive_path = materialized.get(source_id)
        if archive_path is None:
            raise StagingError(f"source {source_id} has not been materialized")
        destination = _destination(
            output, source.get("directory", source.get("path")), source_id
        )
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r") as archive:
            archive.extractall(
                destination,
                members=_safe_members(archive, source_id),
                filter="data",
            )
