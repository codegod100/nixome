from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any


class SourceLockError(Exception):
    pass


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_DESCRIBE_SHA = re.compile(r"(?:^|-)g([0-9a-f]{7,40})$")


def resolve_url(value: str, aliases: dict[str, str]) -> str:
    if "://" in value:
        return value
    if ":" not in value:
        raise SourceLockError(f"source URL has no alias or scheme: {value!r}")
    alias, relative = value.split(":", 1)
    prefix = aliases.get(alias)
    if prefix is None:
        raise SourceLockError(f"unknown source alias {alias!r} in {value!r}")
    return prefix + relative


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SourceLockError(f"{label} is not a SHA-256 digest")
    return value


def _git_commit(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SourceLockError(f"{label} has no immutable Git ref")
    if _GIT_SHA.fullmatch(value):
        return value
    match = _DESCRIBE_SHA.search(value)
    if match:
        return match.group(1)
    raise SourceLockError(f"{label} Git ref does not contain a commit: {value!r}")


def _local_path(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SourceLockError(f"{label} has no local path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise SourceLockError(f"{label} escapes its project: {value!r}")
    return str(path)


def normalize_source(
    source: dict[str, Any],
    *,
    project: str,
    aliases: dict[str, str],
) -> dict[str, Any]:
    kind = source.get("kind")
    label = f"{project} {kind} source"
    common = {
        key: source[key]
        for key in ("directory", "base-dir")
        if key in source
    }
    if kind in {"git_repo", "git_module"}:
        return {
            "fetcher": "git",
            "url": resolve_url(source["url"], aliases),
            "revision": _git_commit(source.get("ref"), label),
            "submodules": kind == "git_module",
            **({"path": source["path"]} if "path" in source else {}),
            **common,
        }
    if kind in {"tar", "zip", "remote"}:
        return {
            "fetcher": kind,
            "url": resolve_url(source["url"], aliases),
            "sha256": _sha256(source.get("ref"), label),
            **({"filename": source["filename"]} if "filename" in source else {}),
            **common,
        }
    if kind in {"local", "patch", "patch_queue"}:
        return {
            "fetcher": kind,
            "project": project,
            "path": _local_path(source.get("path"), label),
            **({"stripLevel": source["strip-level"]} if "strip-level" in source else {}),
            **common,
        }
    if kind == "cpan":
        suffix = source.get("suffix")
        if not isinstance(suffix, str):
            raise SourceLockError(f"{label} has no suffix")
        return {
            "fetcher": "archive",
            "url": resolve_url(f"cpan:{suffix}", aliases),
            "sha256": _sha256(source.get("sha256sum"), label),
        }
    if kind == "pypi":
        ref = source.get("ref")
        if not isinstance(ref, dict) or not isinstance(ref.get("suffix"), str):
            raise SourceLockError(f"{label} has malformed ref")
        return {
            "fetcher": "archive",
            "url": resolve_url(f"pypi:{ref['suffix']}", aliases),
            "sha256": _sha256(ref.get("sha256sum"), label),
        }
    if kind == "go_module":
        ref = source.get("ref")
        if not isinstance(ref, dict):
            raise SourceLockError(f"{label} has malformed ref")
        return {
            "fetcher": "git",
            "url": resolve_url(source["url"], aliases),
            "revision": _git_commit(ref.get("git-ref"), label),
            "module": source.get("module"),
            "goVersion": ref.get("go-version"),
        }
    if kind == "docker":
        return {
            "fetcher": "oci",
            "url": resolve_url(source["url"], aliases),
            "digest": _sha256(source.get("ref"), label),
            "architecture": source.get("architecture"),
        }
    if kind == "cargo2":
        refs = source.get("ref")
        if not isinstance(refs, list):
            raise SourceLockError(f"{label} has malformed crate refs")
        for crate in refs:
            if not isinstance(crate, dict):
                raise SourceLockError(f"{label} has malformed crate")
            if crate.get("kind") == "registry":
                _sha256(crate.get("sha"), f"{label} crate")
            elif crate.get("kind") == "git":
                _git_commit(crate.get("commit"), f"{label} crate")
        return {"fetcher": "cargo", "crates": refs}
    if kind == "gen_cargo_lock":
        ref = source.get("ref")
        if not isinstance(ref, str):
            raise SourceLockError(f"{label} has no embedded lock")
        return {"fetcher": "embedded", "encoding": "base64", "data": ref}
    raise SourceLockError(f"unsupported source kind: {kind!r}")


def lock_sources(
    graph: dict[str, Any], aliases_by_project: dict[str, dict[str, str]]
) -> dict[str, Any]:
    unique: dict[str, dict[str, Any]] = {}
    declarations: dict[str, list[str]] = {}
    for qualified, element in sorted(graph["elements"].items()):
        project = element["project"]
        aliases = aliases_by_project.get(project, {})
        ids = []
        for source in element["sources"]:
            normalized = normalize_source(
                source, project=project, aliases=aliases
            )
            encoded = json.dumps(
                normalized, sort_keys=True, separators=(",", ":")
            ).encode()
            source_id = hashlib.sha256(encoded).hexdigest()
            unique[source_id] = normalized
            ids.append(source_id)
        declarations[qualified] = ids
    return {
        "formatVersion": 1,
        "graphTarget": graph["target"],
        "sources": dict(sorted(unique.items())),
        "elements": declarations,
        "declarationCount": sum(len(ids) for ids in declarations.values()),
        "uniqueSourceCount": len(unique),
    }
