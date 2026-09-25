#!/usr/bin/env python3
"""Persist measured service-failure counts before the partial run is repaired."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = [json.loads(line) for line in (ROOT / "results" / "rows" / "haiku_robustness_sample4_scaffold.jsonl").read_text().splitlines()]
parsed = sum(row["parse_ok"] for row in rows)
empty = sum(not row["response"] for row in rows)
out = {
    "artifact": "AuthentiGrant",
    "event": "Claude CLI session limit during first scaffold command",
    "rows_requested": len(rows),
    "successful_rows_before_limit": parsed,
    "empty_rows": empty,
    "failed_cli_invocations": empty * 2,
    "included_in_model_results": False,
}
(ROOT / "results" / "infrastructure_incident.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(out)
