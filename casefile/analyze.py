"""Deterministic checks over an agent-written branch. Every check produces evidence a human can re-run.

Usage: python analyze.py <repo> <base> <head> <out.json>
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Lines the requirement allows in a regenerated snapshot: the guard, the attribute, and nothing else.
SNAPSHOT_ALLOWED = {
    "#if !NETSTANDARD2_0 && !NETFRAMEWORK",
    "#endif",
    "[global::System.Diagnostics.CodeAnalysis.ExcludeFromCodeCoverage]",
}
# Files whose change is a policy decision, never a reviewer's call.
POLICY_FILES = {
    "Directory.Packages.props": "Dependency and toolchain versions decide which customers can use the package.",
    "Directory.Build.props": "Build-wide settings affect every project in the repository.",
    "global.json": "SDK pinning affects every contributor and CI.",
}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def file_diff(repo, rng, path):
    added, removed = [], []
    for line in git(repo, "diff", "--unified=0", rng, "--", path).splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    return added, removed


def classify(path):
    if path.endswith(".g.cs"):
        return "snapshot"
    if path in POLICY_FILES:
        return "policy"
    if path.endswith(".tt"):
        return "template"
    if "/Transforms/" in path and path.endswith(".cs"):
        return "template-output" if Path(path).with_suffix(".tt").name in TT_NAMES else "generator-code"
    if "Tests" in path:
        return "test"
    if path.endswith(".md"):
        return "docs"
    return "other"


TT_NAMES = set()


def main(repo, base, head, out):
    rng = f"{base}...{head}"
    files = [f for f in git(repo, "diff", "--name-only", "-z", rng).split("\0") if f]
    TT_NAMES.update(Path(f).name for f in files if f.endswith(".tt"))
    numstat = {}
    for line in git(repo, "diff", "--numstat", "-z", rng).split("\0"):
        if line:
            a, d, p = line.split("\t", 2)
            numstat[p] = (int(a), int(d))

    groups = {}
    for f in files:
        groups.setdefault(classify(f), []).append(f)

    checks = []

    # 1. Snapshots: only the allowed lines may be added, nothing removed.
    clean, odd = [], []
    for f in groups.get("snapshot", []):
        added, removed = file_diff(repo, rng, f)
        bad = [l for l in added if l.strip() not in SNAPSHOT_ALLOWED] + [f"-{l}" for l in removed]
        (odd if bad else clean).append({"file": f, "unexpected": bad[:6]})
    checks.append({
        "id": "snapshot-shape",
        "title": "Regenerated snapshots contain only the guarded attribute",
        "method": "Every added line in each .g.cs file must be one of the 3 allowed lines; no line may be removed.",
        "rerun": f"git diff -U0 {rng} -- '*.g.cs' | grep '^[+-]' | grep -v '^+++\\|^---' | sort | uniq -c",
        "passed": len(clean), "failed": len(odd), "exceptions": odd,
    })

    # 2. Each .tt template must change together with its checked-in generated .cs, inserting the same attribute count.
    pairs = []
    for tt in groups.get("template", []):
        cs = tt[:-3] + ".cs"
        tt_add, _ = file_diff(repo, rng, tt)
        cs_add, _ = file_diff(repo, rng, cs) if cs in files else ([], [])
        n_tt = sum("ExcludeFromCodeCoverage" in l for l in tt_add)
        n_cs = sum(l.count("ExcludeFromCodeCoverage") for l in cs_add)
        pairs.append({"template": tt, "generated": cs if cs in files else None, "tt_attrs": n_tt, "cs_attrs": n_cs,
                      "ok": cs in files and n_tt == n_cs})
    checks.append({
        "id": "template-pairs",
        "title": "Each T4 template and its generated C# change together",
        "method": "Count attribute insertions in each .tt and in its .cs twin; they must match.",
        "rerun": f"git diff {rng} -- '*.tt' '*Template.cs' | grep -c ExcludeFromCodeCoverage",
        "passed": sum(p["ok"] for p in pairs), "failed": sum(not p["ok"] for p in pairs), "pairs": pairs,
    })

    # 3. Policy files: report exactly what moved.
    policy = []
    for f in groups.get("policy", []):
        added, removed = file_diff(repo, rng, f)
        policy.append({"file": f, "why": POLICY_FILES[f], "removed": removed, "added": added})
    checks.append({
        "id": "policy-files",
        "title": "Changes to files the reviewer may not decide on",
        "method": "Any change to a policy file is routed to the owner, whatever the diff looks like.",
        "rerun": f"git diff {rng} -- {' '.join(POLICY_FILES)}",
        "passed": 0, "failed": len(policy), "changes": policy,
    })

    # 4. Snapshot line histogram, for the walkthrough.
    hist = Counter()
    for f in groups.get("snapshot", []):
        added, removed = file_diff(repo, rng, f)
        hist.update("+ " + l.strip() for l in added)
        hist.update("- " + l.strip() for l in removed)

    result = {
        "range": rng,
        "head_commit": git(repo, "rev-parse", head).strip(),
        "base_commit": git(repo, "merge-base", base, head).strip(),
        "files_total": len(files),
        "lines": [sum(v[0] for v in numstat.values()), sum(v[1] for v in numstat.values())],
        "groups": {k: [{"file": f, "add": numstat[f][0], "del": numstat[f][1]} for f in v] for k, v in groups.items()},
        "checks": checks,
        "snapshot_histogram": hist.most_common(12),
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: len(v) for k, v in groups.items()}), [(c["id"], c["passed"], c["failed"]) for c in checks])


if __name__ == "__main__":
    main(*sys.argv[1:5])
