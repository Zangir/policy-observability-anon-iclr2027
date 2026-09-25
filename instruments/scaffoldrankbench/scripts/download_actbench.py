"""Download the pinned public release; verify every original publisher file digest."""
import hashlib
import json
from pathlib import Path
import argparse
import requests

ROOT = Path(__file__).resolve().parents[1]
REVISION = "595df032d53ef71f927c9a1d8c068dad0edebbc5"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "data/actbench-source")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    validation = json.loads((ROOT / "results/external_inputs/actbench_source_validation.json").read_text())
    files = validation["source_files"]
    for record in files:
        target = args.out / record["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            url = f"https://huggingface.co/datasets/ZJUICSR/ActBench/resolve/{REVISION}/{record['path']}"
            response = requests.get(url, stream=True, timeout=120)
            response.raise_for_status()
            temporary = target.with_suffix(".part")
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(1048576):
                    handle.write(chunk)
            temporary.rename(target)
        assert target.stat().st_size == record["size_bytes"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == record["sha256"]
        print(record["path"], "verified", flush=True)
    (args.out / "metadata").mkdir(exist_ok=True)
    (args.out / "metadata/data_files.json").write_text(json.dumps(
        {"files": files, "file_count": len(files)}, indent=2) + "\n")


if __name__ == "__main__":
    main()
