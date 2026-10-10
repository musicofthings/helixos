#!/usr/bin/env python3
"""Generate TypeScript types for the ELN contract from the Pydantic models.

Pydantic models in ``helixos/eln/schemas.py`` are the source of truth.

    python scripts/generate_ts_types.py          # (re)write the generated file
    python scripts/generate_ts_types.py --check  # exit 1 if the file is stale

Conventions: enums become string-literal unions. Request models (``*Create``,
``*Update``, ``*Request``) make a field optional (``?``) when it has a default,
matching how clients build payloads. Every other model is a response/shape the
API always serializes in full, so all its fields are required. ``datetime`` is
an ISO string; free-form ``object`` is ``unknown``.
"""

from __future__ import annotations

import argparse
import enum
import sys
from pathlib import Path

from pydantic import BaseModel

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from helixos.eln import schemas  # noqa: E402

OUTPUT = API_ROOT.parents[1] / "packages/types/src/eln.generated.ts"

HEADER = """// AUTO-GENERATED from services/api/helixos/eln/schemas.py — do not edit.
// Regenerate: (cd services/api && python scripts/generate_ts_types.py)
"""


def ts_type(node: dict) -> str:
    if "$ref" in node:
        return node["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in node:
        return " | ".join(dict.fromkeys(ts_type(option) for option in node["anyOf"]))
    if "enum" in node:
        return " | ".join(f'"{value}"' for value in node["enum"])
    kind = node.get("type")
    if kind == "null":
        return "null"
    if kind == "string":
        return "string"
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "array":
        inner = ts_type(node.get("items", {}))
        return f"({inner})[]" if "|" in inner else f"{inner}[]"
    if kind == "object":
        extra = node.get("additionalProperties")
        if isinstance(extra, dict):
            return f"Record<string, {ts_type(extra)}>"
        return "Record<string, unknown>"
    return "unknown"


def render_enum(cls: type[enum.Enum]) -> str:
    members = "\n".join(f'  | "{member.value}"' for member in cls)
    return f"export type {cls.__name__} =\n{members};\n"


INPUT_SUFFIXES = ("Create", "Update", "Request")


def render_model(cls: type[BaseModel]) -> str:
    schema = cls.model_json_schema()
    if cls.__name__.endswith(INPUT_SUFFIXES):
        required = set(schema.get("required", []))
    else:
        required = set(schema.get("properties", {}))
    lines = [f"export interface {cls.__name__} {{"]
    for name, node in schema.get("properties", {}).items():
        optional = "" if name in required else "?"
        lines.append(f"  {name}{optional}: {ts_type(node)};")
    lines.append("}\n")
    return "\n".join(lines)


def generate() -> str:
    # Declaration order of the module keeps the output stable and readable.
    declared = [
        obj
        for obj in vars(schemas).values()
        if isinstance(obj, type) and obj.__module__ == schemas.__name__
    ]
    blocks = []
    for cls in declared:
        if issubclass(cls, enum.Enum):
            blocks.append(render_enum(cls))
        elif issubclass(cls, BaseModel):
            blocks.append(render_model(cls))
    return HEADER + "\n" + "\n".join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if output is stale")
    args = parser.parse_args()

    expected = generate()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != expected:
            print(
                f"{OUTPUT.relative_to(API_ROOT.parents[1])} is stale; run "
                "`python scripts/generate_ts_types.py`",
                file=sys.stderr,
            )
            return 1
        print("TypeScript contract types are up to date")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
