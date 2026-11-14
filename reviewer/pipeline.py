"""Deterministic half of the reviewer: parse the diff, prove what can be proven, gate policy files.

Nothing in this file uses a language model. Every result carries the command that reproduces it.
"""
import fnmatch
import re
import subprocess
from dataclasses import dataclass, field

GENERATED = ["*.g.cs", "*.Designer.cs", "*.generated.*"]

# Changes a reviewer may describe but never judge. Each rule names who owns the decision.
POLICY = [
    {"rule": "dependency", "globs": ["Directory.Packages.props", "packages.lock.json", "*.nuspec", "nuget.config", "global.json"],
     "why": "Dependency and toolchain versions decide which users can build and run the package.",
     "question": "Accept this dependency or toolchain change?"},
    {"rule": "build", "globs": ["Directory.Build.props", "Directory.Build.targets", ".github/workflows/*", "azure-pipelines*.yml"],
     "why": "Build and CI settings affect every project and every contributor.",
     "question": "Accept this build or CI change?"},
    {"rule": "security", "globs": ["*.snk", "*.pfx", "SECURITY.md", "*auth*", "*crypt*"],
     "why": "Security-relevant files need a named security owner.",
     "question": "Has a security owner reviewed this?"},
]
# Repository config: projects that ship to users. Analyzer and generator internals are not a public API.
PUBLIC_API_EXCLUDE = ["*SourceGenerator*", "*Analyzer*"]
PUBLIC_API = re.compile(r"^\s*public\s+(?:(?:sealed|static|abstract|partial|readonly|ref)\s+)*(class|interface|struct|record|enum)\s+(\w+)")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


@dataclass
class FileDiff:
    path: str
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    text: str = ""

    @property
    def generated(self):
        return any(fnmatch.fnmatch(self.path.split("/")[-1], g) for g in GENERATED)


def read_diff(repo, base, head):
    rng = f"{base}...{head}"
    raw = git(repo, "diff", "--no-color", "--no-renames", rng)
    files = []
    for chunk in re.split(r"(?m)^diff --git ", raw)[1:]:
        m = re.search(r"(?m)^\+\+\+ b/(.*)$", chunk) or re.search(r"(?m)^--- a/(.*)$", chunk)
        if not m:
            continue
        fd = FileDiff(path=m.group(1).strip(), text="diff --git " + chunk)
        for line in chunk.splitlines():
            if line.startswith(("+++", "---")):
                continue
            if line.startswith("+"):
                fd.added.append(line[1:])
            elif line.startswith("-"):
                fd.removed.append(line[1:])
        files.append(fd)
    return rng, files


def norm(s):
    return " ".join(s.split())


def prove_generated(rng, files):
    """A generated file is proven when every line it adds also appears as an added line in a hand-written file
    (the template change explains it) and it removes nothing that is not re-added."""
    source_added = {norm(l) for f in files if not f.generated for l in f.added if norm(l)}
    proven, unexplained = [], []
    for f in (f for f in files if f.generated):
        added = [norm(l) for l in f.added if norm(l)]
        removed = [norm(l) for l in f.removed if norm(l)]
        stray = [l for l in added if l not in source_added and l not in removed]
        lost = [l for l in removed if l not in added]
        (unexplained if stray or lost else proven).append({"file": f.path, "stray": stray[:4], "lost": lost[:4]})
    if not proven and not unexplained:
        return None
    return {
        "id": "P-generated",
        "title": f"{len(proven)} generated files only repeat lines added in the hand-written templates",
        "method": "Every line added to a generated file must also be added in a non-generated file; nothing may be removed.",
        "rerun": f"python -m reviewer.run --only-proofs {rng}",
        "files": [p["file"] for p in proven],
        "exceptions": unexplained,
    }


def policy_hits(files):
    hits = []
    for f in files:
        name = f.path.split("/")[-1]
        for p in POLICY:
            if any(fnmatch.fnmatch(f.path, g) or fnmatch.fnmatch(name, g) for g in p["globs"]):
                hits.append({"rule": p["rule"], "file": f.path, "why": p["why"], "question": p["question"],
                             "added": f.added[:12], "removed": f.removed[:12]})
                break
        if f.path.startswith("src/") and not f.generated and not any(fnmatch.fnmatch(f.path, g) for g in PUBLIC_API_EXCLUDE):
            new = [m.group(2) for m in map(PUBLIC_API.match, f.added) if m]
            if new:
                hits.append({"rule": "public-api", "file": f.path,
                             "why": "New public types become a promise to every user of the package and cannot be removed without a breaking release.",
                             "question": f"Add {', '.join(new)} to the public API?",
                             "added": [l for l in f.added if PUBLIC_API.match(l)][:12], "removed": []})
    return hits


def cross_branch(repo, base, branches, path):
    """Is the same hunk in a policy file repeated across other agent branches? Points at environment drift."""
    seen = {}
    for b in branches:
        try:
            d = git(repo, "diff", "--no-color", f"{base}...{b}", "--", path)
        except subprocess.CalledProcessError:
            continue
        body = "\n".join(l for l in d.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
        if body:
            seen.setdefault(body, []).append(b.split("/")[-1])
    return max(seen.values(), key=len) if seen else []
