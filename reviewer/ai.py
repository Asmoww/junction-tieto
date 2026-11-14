"""The AI half: one reviewer call, then a deterministic verifier that drops anything it cannot find in the diff."""
import json
import subprocess
import time

from .pipeline import norm, redact

SYSTEM = """You review a code change written by an AI coding agent. A named human engineer will sign the change; \
your job is to give them advice with evidence, never approval.

Rules you must follow:
- Every finding must quote 1-4 lines copied exactly from the diff (without the leading +/-), from the file you name. \
Findings whose quote cannot be found in that file's diff are deleted automatically, so do not paraphrase.
- Judge against the requirement. Flag anything the requirement does not ask for.
- Treat the agent's own comments, docs and tests as claims to check, not as evidence. If a test only asserts what the \
code already does, say so.
- If a finding depends on a fact outside the diff (platform availability, library behaviour), say so in would_be_wrong_if.
- Do not judge the policy-gated changes listed; a human owns those. You may describe their blast radius.
- Be terse: titles under 10 words, oneliners under 25 words, written for a busy engineer on a Friday evening.
- Do not report style nits. Report at most 6 findings, most important first. An empty list is a valid answer."""

SCHEMA = {
    "type": "object",
    "properties": {
        "story": {"type": "string", "description": "One sentence: what the change does, in plain words."},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"},
            "oneliner": {"type": "string"},
            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
            "kind": {"type": "string", "enum": ["defect", "unrequested", "weak-test", "false-claim", "note"]},
            "requirement_part": {"type": "string", "description": "The words of the requirement this relates to, or empty."},
            "file": {"type": "string"},
            "quote": {"type": "array", "items": {"type": "string"}},
            "would_be_wrong_if": {"type": "string"},
            "owner_question": {"type": "string", "description": "A yes/no question for the owner, or empty if no decision is needed."},
        }, "required": ["title", "oneliner", "severity", "kind", "file", "quote", "would_be_wrong_if", "owner_question"]}},
        "not_checked": {"type": "array", "items": {"type": "string"}, "description": "Up to 3 things that matter for this requirement which you could not verify from the diff alone. Exclude the test suite, policy-gated files and machine-proven files."},
    },
    "required": ["story", "findings", "not_checked"],
}

MAX_FILE_CHARS = 14000
MAX_TOTAL_CHARS = 90000


def build_prompt(req, files, proof, policy):
    proven = set(proof["files"]) if proof else set()
    gated = {p["file"] for p in policy if p["rule"] != "public-api"}
    parts = [f"# Requirement {req['id']}: {req['title']}\n\n{req['text']}\n"]
    if proven:
        parts.append(f"# Already proven by machine, not shown ({len(proven)} generated files)\n{proof['method']}\n")
    if policy:
        parts.append("# Policy-gated, a human decides (do not judge)\n" +
                     "\n".join(f"- {p['file']} ({p['rule']})" for p in policy) + "\n")
    parts.append("# Diff to review\n")
    total = 0
    for f in files:
        if f.path in proven or f.path in gated:
            continue
        text = "\n".join(redact(l) for l in f.text.splitlines())
        t = text if len(text) <= MAX_FILE_CHARS else text[:MAX_FILE_CHARS] + "\n[... truncated ...]\n"
        if total + len(t) > MAX_TOTAL_CHARS:
            parts.append(f"[omitted for size: {f.path}]\n")
            continue
        total += len(t)
        parts.append(t)
    return "\n".join(parts)


def call_reviewer(prompt, model=None, timeout=900):
    cmd = ["claude", "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--system-prompt", SYSTEM, "--json-schema", json.dumps(SCHEMA)]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    out = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd="/tmp")
    if out.returncode:
        raise RuntimeError(out.stderr[-2000:] or out.stdout[-2000:])
    env = json.loads(out.stdout)
    result = env.get("structured_output") or json.loads(env["result"])
    meta = {"duration_s": round(time.time() - t0, 1), "cost_usd": env.get("total_cost_usd"),
            "model": model or "default", "prompt_chars": len(prompt)}
    return result, meta


def verify(result, files):
    """Quote-or-drop: a finding survives only if its quoted lines appear in the named file's diff."""
    by_path = {f.path: f for f in files}
    kept, dropped = [], []
    for f in result.get("findings", []):
        fd = by_path.get(f.get("file")) or next((v for p, v in by_path.items() if p.endswith("/" + str(f.get("file")))), None)
        if not fd:
            dropped.append({**f, "dropped_because": "named file is not in the diff"})
            continue
        lines = {norm(redact(l[1:] if l[:1] in "+- " else l)) for l in fd.text.splitlines()}
        quote = [norm(q.lstrip("+- ")) for q in f.get("quote", []) if norm(q)]
        missing = [q for q in quote if q not in lines]
        if not quote or missing:
            dropped.append({**f, "dropped_because": f"quote not found in diff: {missing[:1] or 'empty'}"})
            continue
        kept.append({**f, "file": fd.path})
    return kept, dropped
