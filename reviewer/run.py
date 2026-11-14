"""Review one agent branch end to end and write its case file.

python -m reviewer.run --repo sample-repo --base origin/master --head origin/ju26-issue-2297 \
    --req requirements/REQ-2297.json --out data/cases/2297.json
"""
import argparse
import json
import re
from pathlib import Path

from . import ai
from .pipeline import cross_branch, git, policy_hits, prove_generated, read_diff

RULE_NAMES = {"dependency": "Dependency", "build": "Build", "security": "Security", "public-api": "Public API", "secret": "Credential"}
NOT_CHECKED_ALWAYS = ["The test suite was not run (no .NET SDK on the review host)."]


def route(findings, policy):
    """Explainable routing, no scores: these rules decide what reaches the owner."""
    decisions, handled = [], []
    for i, p in enumerate(policy, 1):
        decisions.append({"id": f"R{i}", "status": "refused", "severity": "high", "title": f"{RULE_NAMES[p['rule']]} change in {p['file'].split('/')[-1]}",
                          "oneliner": p["why"], "file": p["file"], "quote": p["removed"][:3] and [f"- {l}" for l in p["removed"][:3]] + [f"+ {l}" for l in p["added"][:3]] or p["added"][:4],
                          "question": p["question"], "routed_by": f"policy rule '{p['rule']}': the reviewer may not decide this",
                          "seen_in": p.get("seen_in", [])})
    for i, f in enumerate(findings, 1):
        item = {"id": f"F{i}", "severity": f["severity"], "title": f["title"], "oneliner": f["oneliner"], "file": f["file"],
                "quote": f["quote"], "kind": f["kind"], "requirement_part": f.get("requirement_part", ""),
                "would_be_wrong_if": f["would_be_wrong_if"], "question": f.get("owner_question", ""), "evidence": f.get("evidence", [])}
        needs_owner = f["severity"] == "high" or (f["severity"] == "medium" and f["kind"] in {"defect", "false-claim", "unrequested"})
        if needs_owner and item["question"]:
            item["status"] = "contested"
            item["routed_by"] = f"{f['severity']} severity {f['kind']}"
            decisions.append(item)
        else:
            item["status"] = "weak-evidence" if f["kind"] == "weak-test" else "supported"
            item["routed_by"] = "low impact or no decision needed"
            handled.append(item)
    return decisions, handled


def attach_evidence(findings, probes):
    for f in findings:
        text = " ".join([f["title"], f["oneliner"], f["would_be_wrong_if"], *f["quote"]])
        f["evidence"] = [{k: p[k] for k in ("label", "result", "rerun")} for p in probes if re.search(p["match"], text, re.I)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--req", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--probes", help="JSON list of extra machine evidence {match, label, result, rerun}")
    ap.add_argument("--siblings", nargs="*", default=[], help="Other agent branches, to spot repeated policy hunks")
    ap.add_argument("--model")
    a = ap.parse_args()

    req = json.loads(Path(a.req).read_text())
    rng, files = read_diff(a.repo, a.base, a.head)
    proof = prove_generated(rng, files)
    policy = policy_hits(files)
    for p in policy:
        if p["rule"] != "public-api" and a.siblings:
            p["seen_in"] = cross_branch(a.repo, a.base, [a.head, *a.siblings], p["file"])

    prompt = ai.build_prompt(req, files, proof, policy)
    result, meta = ai.call_reviewer(prompt, a.model)
    kept, dropped = ai.verify(result, files)
    attach_evidence(kept, json.loads(Path(a.probes).read_text()) if a.probes else [])
    decisions, handled = route(kept, policy)

    proven_files = set(proof["files"]) if proof else set()
    case = {
        "id": req["id"].split("-")[-1],
        "requirement": req,
        "branch": a.head.split("/")[-1],
        "base_commit": git(a.repo, "merge-base", a.base, a.head).strip(),
        "head_commit": git(a.repo, "rev-parse", a.head).strip(),
        "story": result.get("story", "").replace("`", ""),
        "stats": {
            "files": len(files),
            "added": sum(len(f.added) for f in files),
            "removed": sum(len(f.removed) for f in files),
            "files_proven": len(proven_files),
            "decisions": len(decisions),
            "findings_kept": len(kept),
            "findings_dropped": len(dropped),
        },
        "proof": proof,
        "decisions": decisions,
        "handled": handled,
        "dropped": [{"title": d.get("title"), "file": d.get("file"), "dropped_because": d["dropped_because"]} for d in dropped],
        "not_checked": NOT_CHECKED_ALWAYS + [n for n in result.get("not_checked", []) if "test suite" not in n.lower()][:4],
        "reviewer": meta,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(case, indent=2, ensure_ascii=False))
    print(json.dumps(case["stats"]), meta)


if __name__ == "__main__":
    main()
