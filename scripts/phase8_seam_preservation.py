"""Read-only content preservation audit against the pre-implementation hashes."""
import hashlib
import json
from pathlib import Path


def main():
    workspace = Path(__file__).resolve().parents[1]
    baseline = json.loads((workspace / "phase8-preservation-baseline.json").read_text())
    report = {}
    for name, root in (("original", Path("C:/PROJECTS/ARIA")), ("isolated", workspace)):
        changed, missing = [], []
        for relative, digest in baseline[name].items():
            path = root / relative
            if not path.is_file():
                missing.append(relative)
            elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                changed.append(relative)
        report[name] = {"files_checked":len(baseline[name]), "changed":changed, "missing":missing}
    report["preserved"] = (not report["original"]["changed"] and not report["original"]["missing"]
                           and report["isolated"]["changed"] == ["src/aria/shard_presentation.py"]
                           and not report["isolated"]["missing"])
    print(json.dumps(report, indent=2))
    (workspace / "docs/evidence/phase8-preservation-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["preserved"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
