"""Freeze or run the separately planned safety observation studies."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from compositional_harm_bench.followup import binding_requests, external_requests
from recorded_safety_subject import run_requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("study", choices=["binding", "external"])
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    inputs = root / "results/external_inputs"
    if args.study == "binding":
        requests = binding_requests()
        repeats = 2
    else:
        source = inputs / "atbench-test.json"
        selection = json.loads((inputs / "ATBENCH_SELECTION.json").read_text())
        assert hashlib.sha256(source.read_bytes()).hexdigest() == selection["source_sha256"]
        requests = external_requests(json.loads(source.read_text()), selection)
        repeats = 1
    out = root / "results" / ("binding_repair_v1" if args.study == "binding" else "atbench_observation_v1")
    out.mkdir(exist_ok=True)
    encoded = json.dumps(requests, sort_keys=True, ensure_ascii=False).encode()
    frozen = out / "frozen_requests.json"
    record = {"study": args.study, "n_requests": len(requests), "repeats": repeats,
              "n_model_calls": len(requests) * repeats * 2,
              "requests_sha256": hashlib.sha256(encoded).hexdigest(), "requests": requests}
    if frozen.exists():
        assert json.loads(frozen.read_text()) == record, "Frozen inputs changed"
    elif args.freeze:
        frozen.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        (out / "FROZEN_AT.json").write_text(json.dumps({
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "sha256": record["requests_sha256"]}, indent=2) + "\n")
    else:
        raise RuntimeError("Freeze and inspect requests before collecting responses")
    if args.offline:
        print(args.study, len(requests), "design rows;", record["n_model_calls"], "planned model calls")
        return
    responses = run_requests(requests, out, repeats=repeats, seed=20270912,
                             workers=3, timeout=180)
    print("Complete", args.study, len(responses), "recorded responses")


if __name__ == "__main__":
    main()
