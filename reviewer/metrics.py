"""Compute the trust measurements from spot-checks, planted defects and repeat runs. No AI involved."""
import json
from pathlib import Path

from .pipeline import norm

DATA = Path(__file__).resolve().parent.parent / "data"
EVID = Path(__file__).resolve().parent.parent / "evidence"
CASES = ["2283", "2234", "2129", "2297"]


def same(a, b):
    """Two findings match when they name the same file and share a quoted line."""
    qa = {norm(q.lstrip("+- ")) for q in a["quote"]}
    qb = {norm(q.lstrip("+- ")) for q in b["quote"]}
    return a["file"] == b["file"] and bool(qa & qb)


def main():
    out = {"cases": {}}
    verdicts = {"true": 0, "partly": 0, "false": 0, "unverifiable": 0}
    routed = {"true": 0, "partly": 0, "false": 0, "unverifiable": 0}
    files = proven = decisions = 0
    for n in CASES:
        case = json.loads((DATA / "cases" / f"{n}.json").read_text())
        files += case["stats"]["files"]
        proven += case["stats"]["files_proven"]
        decisions += case["stats"]["decisions"]
        routed_ids = {d["id"] for d in case["decisions"]}
        sc = json.loads((DATA / "spotcheck" / f"{n}.json").read_text())["results"]
        for r in sc:
            verdicts[r["verdict"]] += 1
            if r["id"] in routed_ids:
                routed[r["verdict"]] += 1
        runs = [case] + [json.loads(p.read_text()) for p in sorted((DATA / "stability").glob(f"{n}-r*.json"))]
        first = [f for f in case["decisions"] + case["handled"] if f["id"].startswith("F")]
        repro = []
        for f in first:
            others = [r for r in runs[1:]]
            hits = sum(any(same(f, g) for g in r["decisions"] + r["handled"] if g["id"].startswith("F")) for r in others)
            repro.append(hits / len(others) if others else None)
        out["cases"][n] = {
            "runs": len(runs),
            "decisions_per_run": [r["stats"]["decisions"] for r in runs],
            "findings_per_run": [r["stats"]["findings_kept"] for r in runs],
            "policy_per_run": [sum(d["id"].startswith("R") for d in r["decisions"]) for r in runs],
            "reproduced": round(sum(x for x in repro if x is not None) / len([x for x in repro if x is not None]), 2) if repro and runs[1:] else None,
            "spotcheck": {k: sum(r["verdict"] == k for r in sc) for k in verdicts},
            "seconds": [r["reviewer"]["duration_s"] for r in runs],
        }
    planted = json.loads((EVID / "planted.json").read_text())
    d = planted["defects"]
    out["spotcheck"] = verdicts
    out["spotcheck_routed"] = routed
    out["planted"] = {
        "total": len(d), "caught": sum(x["caught"] for x in d),
        "machine": [sum(x["caught"] for x in d if x["layer"] == "machine"), sum(x["layer"] == "machine" for x in d)],
        "ai": [sum(x["caught"] for x in d if x["layer"] == "AI"), sum(x["layer"] == "AI" for x in d)],
        "defects": d, "excluded": planted["excluded"],
    }
    out["routing"] = {"files": files, "proven": proven, "decisions": decisions, "changes": len(CASES)}
    secs = [s for c in out["cases"].values() for s in c["seconds"]]
    out["review_seconds"] = round(sum(secs) / len(secs), 1)
    all_repro = [c["reproduced"] for c in out["cases"].values() if c["reproduced"] is not None]
    out["reproduced"] = round(sum(all_repro) / len(all_repro), 2) if all_repro else None
    (DATA / "metrics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ("spotcheck", "spotcheck_routed", "routing", "review_seconds", "reproduced")}))
    for n, c in out["cases"].items():
        print(n, c["decisions_per_run"], c["findings_per_run"], c["reproduced"])


if __name__ == "__main__":
    main()
