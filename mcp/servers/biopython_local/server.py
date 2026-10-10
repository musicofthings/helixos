#!/usr/bin/env python3
"""HelixOS stdio connector for local sequence analysis.

Speaks newline-delimited JSON. The desktop host sends one request per line and
expects one response per line. This keeps the starter server dependency-free.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable


def _clean_dna(sequence: str) -> str:
    return "".join(base for base in sequence.upper() if base in {"A", "C", "G", "T"})


def analyze_sequence(sequence: str) -> dict[str, Any]:
    """Return basic sequence statistics.

    Only unambiguous A/C/G/T bases are counted; IUPAC ambiguity codes and any
    other characters are silently discarded before computing length and GC%.
    """
    if not isinstance(sequence, str):
        raise TypeError("sequence must be a string")
    clean = _clean_dna(sequence)
    if not clean:
        return {"length": 0, "gc_percent": 0.0, "message": "No valid DNA bases found"}

    gc_count = sum(1 for base in clean if base in {"G", "C"})
    gc_percent = round((gc_count / len(clean)) * 100, 2)
    return {
        "length": len(clean),
        "gc_percent": gc_percent,
        "message": "Computed with HelixOS local sequence analyzer",
    }


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "analyze_sequence": analyze_sequence,
}


def handle_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a single JSON request."""
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return {"id": request_id, "error": {"message": "params must be an object"}}

    if method == "tools/list":
        return {
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": f"Run {name} on local sequence input",
                    }
                    for name in TOOLS
                ]
            },
        }

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {"id": request_id, "error": {"message": "arguments must be an object"}}
        if not isinstance(tool_name, str) or tool_name not in TOOLS:
            return {
                "id": request_id,
                "error": {"message": f"Unknown tool: {tool_name}"},
            }
        try:
            result = TOOLS[tool_name](**arguments)
        except Exception as exc:  # noqa: BLE001 - one bad request must not kill the connector
            return {"id": request_id, "error": {"message": f"{type(exc).__name__}: {exc}"}}
        return {"id": request_id, "result": result}

    return {"id": request_id, "error": {"message": f"Unsupported method: {method}"}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"error": {"message": "Invalid JSON"}}), flush=True)
            continue
        if not isinstance(payload, dict):
            print(json.dumps({"error": {"message": "Request must be an object"}}), flush=True)
            continue
        try:
            response = handle_request(payload)
        except Exception as exc:  # noqa: BLE001 - final per-request boundary
            response = {"id": payload.get("id"), "error": {"message": f"Internal error: {exc}"}}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
