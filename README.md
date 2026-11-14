# Earned Trust in AI Code

Junction 2026, Tieto challenge. An AI code review concept where **AI reviews and a named human stays accountable**.

Live: https://tieto.psavela.com · Play: https://tieto.psavela.com/play

## The idea

An AI agent writes a 238-file pull request. Your name goes on the approval. Instead of reading the diff, you get a case file:

1. **Prove**: deterministic checks clear what can be proven (generated files that only repeat template lines).
2. **Gate**: dependencies, public API, credentials and build files always go to a human. The AI may describe them, never judge them.
3. **Review**: one AI call reads what is left, against the requirement.
4. **Verify**: quote-or-drop. A finding must quote real diff lines or it is deleted.
5. **Route**: named rules, no risk scores, decide what reaches the owner.
6. **Sign**: the owner answers the decisions, accepts what was not checked, and signs. The signature is bound to the commit and an evidence hash.

## Pages

| Path | What |
|---|---|
| `/` | The story: why approval is needed |
| `/play` | 90-second game: would you sign it? |
| `/concept` | Concept card: principles, trade-offs, limits |
| `/cases` | The reviewer on four real agent-written changes |
| `/metrics` | Spot-check precision, planted-defect recall, stability |
| `/log` | Decision and failure-mode log |

## Run it

```bash
git clone https://github.com/te-industry-tech-office/junction26-messagepack-csharp sample-repo
git -C sample-repo fetch origin 'refs/heads/ju26-*:refs/remotes/origin/ju26-*'

# Review one agent branch (needs the `claude` CLI for the AI step)
python3 -m reviewer.run --repo sample-repo --base origin/master --head origin/ju26-issue-2297 \
  --req requirements/REQ-2297.json --out data/cases/2297.json --probes evidence/probes.json

python3 -m reviewer.metrics     # recompute measurements
python3 server.py               # serve on :5203
```

Code: `reviewer/pipeline.py` (deterministic checks and policy gate), `reviewer/ai.py` (reviewer call and quote verifier), `reviewer/run.py` (routing and case file), `reviewer/metrics.py`.
