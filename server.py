"""Case-file demo server: static page, case data, and an append-only sign-off log. Stdlib only."""
import hashlib
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOG = DATA / "signoffs.jsonl"
GAME = DATA / "game.jsonl"
PORT = int(os.environ.get("PORT", "5203"))


def load_case(change):
    case = json.loads((DATA / "cases" / f"{change}.json").read_text())
    # The sign-off binds to this exact evidence: if the commit or any finding changes, the hash changes.
    blob = json.dumps(case, sort_keys=True).encode()
    case["evidence_hash"] = hashlib.sha256(blob).hexdigest()[:16]
    return case


def read_log():
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]


def game_stats():
    rows = [json.loads(l) for l in GAME.read_text().splitlines() if l.strip()] if GAME.exists() else []
    n = len(rows)
    if not n:
        return {"players": 0}
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else 0
    return {
        "players": n,
        "r1_approved": sum(r["r1"]["choice"] != "reject" for r in rows),
        "r1_ai": sum(r["r1"]["choice"] == "ai" for r in rows),
        "r1_secs": avg([r["r1"]["secs"] for r in rows]),
        "r2_secs": avg([r["r2"]["secs"] for r in rows]),
        "r2_fix_f1": sum(r["r2"]["F1"] == "Fix before merge" for r in rows),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "web"), **kw)

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/case/"):
            change = self.path.rsplit("/", 1)[-1]
            if not change.isdigit():
                return self.send_json({"error": "bad id"}, 400)
            try:
                return self.send_json(load_case(change))
            except FileNotFoundError:
                return self.send_json({"error": "unknown change"}, 404)
        if self.path == "/api/cases":
            cases = [json.loads(p.read_text()) for p in sorted((DATA / "cases").glob("*.json"))]
            return self.send_json([{"id": c["id"], "title": c["requirement"]["title"], "branch": c["branch"],
                                    "stats": c["stats"], "story": c["story"]} for c in cases])
        if self.path == "/api/metrics":
            return self.send_json(json.loads((DATA / "metrics.json").read_text()))
        if self.path == "/api/log":
            body = (ROOT / "DECISIONS.md").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/game/stats":
            return self.send_json(game_stats())
        if self.path == "/api/signoffs":
            return self.send_json(read_log())
        if self.path.split("?")[0] in ("/play", "/table", "/cases", "/case", "/concept", "/metrics", "/log"):
            self.path = self.path.replace(self.path.split("?")[0], self.path.split("?")[0] + ".html", 1)
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/game":
            return self.save_game()
        if self.path != "/api/signoff":
            return self.send_json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        if n > 20000:
            return self.send_json({"error": "too large"}, 413)
        try:
            s = json.loads(self.rfile.read(n))
        except ValueError:
            return self.send_json({"error": "bad json"}, 400)
        owner = str(s.get("owner", "")).strip()[:80]
        decision = s.get("decision")
        if not owner or decision not in {"accept", "accept-with-conditions", "reject"}:
            return self.send_json({"error": "A named owner and a decision are required."}, 400)
        case = load_case(str(s.get("change", "")))
        if s.get("evidence_hash") != case["evidence_hash"]:
            return self.send_json({"error": "Evidence changed since you loaded it. Reload and review again."}, 409)
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "change": case["id"],
            "requirement": case["requirement"]["id"],
            "commit": case["head_commit"],
            "evidence_hash": case["evidence_hash"],
            "owner": owner,
            "decision": decision,
            "answers": {k: str(v)[:500] for k, v in (s.get("answers") or {}).items()},
            "residual_risk": str(s.get("residual_risk", ""))[:1000],
            "spot_checked": [str(x)[:40] for x in (s.get("spot_checked") or [])][:20],
        }
        DATA.mkdir(exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return self.send_json(entry, 201)

    def save_game(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > 4000:
            return self.send_json({"error": "too large"}, 413)
        try:
            g = json.loads(self.rfile.read(n))
            r1, r2 = g["r1"], g["r2"]
            entry = {
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "name": str(g.get("name", ""))[:40],
                "r1": {"choice": r1["choice"] if r1["choice"] in {"approve", "reject", "ai"} else "approve",
                       "secs": min(float(r1["secs"]), 999)},
                "r2": {"F1": str(r2.get("F1", ""))[:40], "R1": str(r2.get("R1", ""))[:40], "secs": min(float(r2["secs"]), 999)},
            }
        except (ValueError, KeyError, TypeError):
            return self.send_json({"error": "bad game result"}, 400)
        DATA.mkdir(exist_ok=True)
        with GAME.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return self.send_json(game_stats(), 201)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
