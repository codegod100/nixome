from __future__ import annotations

import ast
import operator
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import yaml


class CompositionError(Exception):
    pass


_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}


def evaluate_condition(expression: str, options: dict[str, Any]) -> bool:
    """Evaluate the deliberately small expression language used by BST options."""

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name):
            if node.id not in options:
                raise CompositionError(f"unknown option in condition: {node.id}")
            return options[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [visit(value) for value in node.elts]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not visit(node.operand)
        if isinstance(node, ast.BoolOp):
            values = [bool(visit(value)) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for operation, comparator in zip(node.ops, node.comparators):
                function = _COMPARE.get(type(operation))
                if function is None:
                    raise CompositionError("unsupported comparison operator")
                right = visit(comparator)
                if not function(left, right):
                    return False
                left = right
            return True
        raise CompositionError(f"unsupported condition syntax: {ast.dump(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise CompositionError(f"invalid condition {expression!r}") from error
    return bool(visit(tree))


def _merge(base: Any, overlay: Any) -> Any:
    if isinstance(overlay, dict) and set(overlay) == {"(>)"}:
        append = overlay["(>)"]
        if not isinstance(base, list) or not isinstance(append, list):
            raise CompositionError("(>) requires a list composition")
        return [*base, *append]
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = dict(base)
        for key, value in overlay.items():
            if key in {"(@)", "(?)"}:
                continue
            result[key] = _merge(result[key], value) if key in result else value
        return result
    return overlay


def load_composed(
    path: Path,
    *,
    project_root: Path,
    options: dict[str, Any],
    external_include: Callable[[str], Any] | None = None,
    stack: tuple[Path, ...] = (),
) -> Any:
    path = path.resolve()
    project_root = project_root.resolve()
    if path in stack:
        chain = " -> ".join(str(item) for item in (*stack, path))
        raise CompositionError(f"include cycle: {chain}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CompositionError(f"cannot read {path}: {error}") from error

    def compose(value: Any) -> Any:
        if isinstance(value, list):
            result = []
            for item in value:
                composed = compose(item)
                if isinstance(composed, dict) and set(composed) == {"(>)"}:
                    extension = composed["(>)"]
                    if not isinstance(extension, list):
                        raise CompositionError("(>) requires a list")
                    result.extend(extension)
                else:
                    result.append(composed)
            return result
        if not isinstance(value, dict):
            return value
        if set(value) == {"(>)"}:
            extension = value["(>)"]
            if not isinstance(extension, list):
                raise CompositionError("(>) requires a list")
            return {"(>)": compose(extension)}

        result: dict[str, Any] = {}
        includes = value.get("(@)", [])
        if isinstance(includes, str):
            includes = [includes]
        if not isinstance(includes, list):
            raise CompositionError("(@) must be a path or list of paths")
        for include in includes:
            if not isinstance(include, str):
                raise CompositionError("include path must be a string")
            if ":" in include:
                if external_include is None:
                    raise CompositionError(f"unresolved junction include: {include}")
                included = external_include(include)
            else:
                relative = PurePosixPath(include)
                if relative.is_absolute() or ".." in relative.parts:
                    raise CompositionError(f"include escapes project: {include}")
                included = load_composed(
                    project_root / relative,
                    project_root=project_root,
                    options=options,
                    external_include=external_include,
                    stack=(*stack, path),
                )
            result = _merge(result, included)

        ordinary = {
            key: compose(item)
            for key, item in value.items()
            if key not in {"(@)", "(?)"}
        }
        result = _merge(result, ordinary)

        conditionals = value.get("(?)", [])
        if isinstance(conditionals, dict):
            conditionals = [conditionals]
        if not isinstance(conditionals, list):
            raise CompositionError("(?) must be a list")
        for choices in conditionals:
            if not isinstance(choices, dict):
                raise CompositionError("conditional choice must be a mapping")
            for expression, fragment in choices.items():
                if evaluate_condition(str(expression), options):
                    result = _merge(result, compose(fragment))
        return result

    return compose(document)
