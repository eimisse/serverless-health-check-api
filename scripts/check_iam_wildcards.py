#!/usr/bin/env python3
"""Fail CI when Terraform IAM policies introduce unreviewed wildcard permissions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

STRING_RE = re.compile(r'"((?:\\.|[^"\\])*)"')
SID_RE = re.compile(r'\b(?:sid|Sid)\s*=\s*"([A-Za-z0-9_-]+)"')
ACTION_ASSIGN_RE = re.compile(r"\b(?:actions|Action)\s*=")
ACTION_WILDCARD_RE = re.compile(r"^[a-z0-9-]+:\*$", re.IGNORECASE)


def _strip_line_comment(line: str) -> str:
    """Remove HCL line comments without treating comment markers inside strings as comments."""
    in_string = False
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and in_string:
            escaped = True
            index += 1
            continue
        if char == '"':
            in_string = not in_string
            index += 1
            continue
        if not in_string and char == "#":
            return line[:index]
        if not in_string and char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            return line[:index]
        index += 1
    return line


def _strip_block_comments(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Remove HCL block comments while preserving slash-star sequences inside strings."""
    cleaned: list[str] = []
    index = 0
    in_string = False
    escaped = False

    while index < len(line):
        if in_block_comment:
            end = line.find("*/", index)
            if end == -1:
                return "".join(cleaned), True
            in_block_comment = False
            index = end + 2
            continue

        char = line[index]
        if escaped:
            cleaned.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\" and in_string:
            cleaned.append(char)
            escaped = True
            index += 1
            continue
        if char == '"':
            in_string = not in_string
            cleaned.append(char)
            index += 1
            continue
        if not in_string and line.startswith("/*", index):
            in_block_comment = True
            index += 2
            continue

        cleaned.append(char)
        index += 1

    return "".join(cleaned), in_block_comment


def _decode_hcl_string(value: str) -> str:
    """Decode the simple escapes used in the Terraform sources we inspect."""
    return value.replace(r'\"', '"').replace(r"\\", "\\")


def _nearest_sid(lines: list[str], line_number: int) -> str | None:
    """Return the closest statement Sid/sid preceding a wildcard occurrence."""
    lower_bound = max(0, line_number - 100)
    for index in range(line_number - 1, lower_bound - 1, -1):
        line, _ = _strip_block_comments(lines[index], False)
        match = SID_RE.search(_strip_line_comment(line))
        if match:
            return match.group(1)
    return None


def _square_bracket_delta(text: str) -> int:
    """Count HCL list brackets outside quoted strings."""
    delta = 0
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "[":
            delta += 1
        elif char == "]":
            delta -= 1
    return delta


def _action_wildcard_locations(lines: list[str]) -> set[tuple[int, str]]:
    """Find literal wildcard values assigned directly to IAM Action/actions fields."""
    locations: set[tuple[int, str]] = set()
    in_block_comment = False
    action_list_depth = 0

    for line_index, raw_line in enumerate(lines, start=1):
        line, in_block_comment = _strip_block_comments(raw_line, in_block_comment)
        code = _strip_line_comment(line)

        segment: str | None = None
        if action_list_depth > 0:
            segment = code
        else:
            assignment = ACTION_ASSIGN_RE.search(code)
            if assignment:
                segment = code[assignment.end() :]

        if segment is None:
            continue

        for match in STRING_RE.finditer(segment):
            literal = _decode_hcl_string(match.group(1))
            if literal == "*" or ACTION_WILDCARD_RE.fullmatch(literal):
                locations.add((line_index, literal))

        delta = _square_bracket_delta(segment)
        if action_list_depth > 0:
            action_list_depth = max(0, action_list_depth + delta)
        elif delta > 0:
            action_list_depth = delta

    return locations


def _is_suspicious_wildcard(literal: str) -> bool:
    if "*" not in literal:
        return False
    if literal == "*":
        return True
    if ACTION_WILDCARD_RE.fullmatch(literal):
        return True
    return (
        literal.startswith("arn:")
        or literal.startswith("${")
        or "/*" in literal
        or literal.endswith(":*")
    )


def _source_files(root: Path) -> Iterable[Path]:
    for base in (root / "bootstrap", root / "terraform"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.tf")):
            if "tests" in path.parts:
                continue
            if ".terraform" in path.parts:
                continue
            yield path


def _catalog_paths(primary: Path) -> list[Path]:
    """Return the primary exception catalogue and optional narrowly scoped supplements."""
    supplements = sorted(primary.parent.glob(f"{primary.stem}.*{primary.suffix}"))
    return [primary, *[path for path in supplements if path != primary]]


def _load_catalog(path: Path) -> list[dict[str, object]]:
    seen_ids: set[str] = set()
    normalized: list[dict[str, object]] = []

    for catalog_path in _catalog_paths(path):
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        entries = data.get("exceptions")
        if not isinstance(entries, list):
            raise ValueError(f"{catalog_path}: catalog must contain an 'exceptions' list")

        for raw in entries:
            if not isinstance(raw, dict):
                raise ValueError(f"{catalog_path}: each exception must be an object")
            required = {"id", "path", "sid", "literal", "expected_count", "reason"}
            missing = required - raw.keys()
            if missing:
                raise ValueError(
                    f"{catalog_path}: exception is missing fields: {sorted(missing)}"
                )
            exception_id = raw["id"]
            if not isinstance(exception_id, str) or not exception_id:
                raise ValueError(f"{catalog_path}: exception id must be a non-empty string")
            if exception_id in seen_ids:
                raise ValueError(f"duplicate exception id: {exception_id}")
            seen_ids.add(exception_id)
            if not isinstance(raw["expected_count"], int) or raw["expected_count"] < 1:
                raise ValueError(f"{exception_id}: expected_count must be a positive integer")
            if not isinstance(raw["reason"], str) or len(raw["reason"].strip()) < 20:
                raise ValueError(f"{exception_id}: reason must be explicit")
            normalized.append(raw)

    return normalized


def audit(root: Path, catalog_path: Path) -> list[str]:
    exceptions = _load_catalog(catalog_path)
    allowed = {
        (str(entry["path"]), entry["sid"], str(entry["literal"])): int(entry["expected_count"])
        for entry in exceptions
    }
    observed: Counter[tuple[str, str | None, str]] = Counter()
    errors: list[str] = []

    for path in _source_files(root):
        rel_path = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        action_wildcards = _action_wildcard_locations(lines)
        in_block_comment = False
        for line_index, raw_line in enumerate(lines, start=1):
            line, in_block_comment = _strip_block_comments(raw_line, in_block_comment)
            code = _strip_line_comment(line)
            for match in STRING_RE.finditer(code):
                literal = _decode_hcl_string(match.group(1))
                if not _is_suspicious_wildcard(literal):
                    continue

                sid = _nearest_sid(lines, line_index)
                key = (rel_path, sid, literal)
                observed[key] += 1

                # Action wildcards are an absolute policy violation and cannot be
                # legitimized by adding an exception catalogue entry.
                if (line_index, literal) in action_wildcards or ACTION_WILDCARD_RE.fullmatch(literal):
                    errors.append(
                        f"{rel_path}:{line_index}: wildcard IAM action '{literal}' is prohibited"
                    )
                    continue

                max_count = allowed.get(key, 0)
                if observed[key] > max_count:
                    errors.append(
                        f"{rel_path}:{line_index}: unreviewed wildcard '{literal}' "
                        f"(sid={sid!r})"
                    )

    for key, expected in sorted(allowed.items(), key=lambda item: repr(item[0])):
        actual = observed.get(key, 0)
        if actual != expected:
            path, sid, literal = key
            errors.append(
                f"catalog mismatch for {path} sid={sid!r} literal={literal!r}: "
                f"expected {expected}, observed {actual}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("security/iam-wildcard-exceptions.json"),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    catalog = args.catalog if args.catalog.is_absolute() else root / args.catalog
    try:
        errors = audit(root, catalog)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"IAM wildcard audit configuration error: {exc}", file=sys.stderr)
        return 2

    if errors:
        print("IAM wildcard audit FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("IAM wildcard audit passed: all wildcard permissions are reviewed and catalogued.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
