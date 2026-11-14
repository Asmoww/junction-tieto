# Hackathon (pikkuinen)

Standing context for the `pikkuinen-hackathon` Claude session. Keep this file current.

## Goal

Junction 2026, Tieto challenge "Earned Trust in AI Code": an AI code review concept where AI reviews
and a named human stays accountable. 24 h to submit (started 2026-11-14). Judged on clarity 30%,
practicality 25%, measurement 25%, evidence 20%. Deliverables: concept card, live walkthrough,
lessons/decision log, demo video. Input repo: github.com/te-industry-tech-office/junction26-messagepack-csharp
(branches ju26-issue-2283, -2234, -2129, -2297). Status: demo v1 live at https://tieto.psavela.com (user service tieto-casefile, port 5203, server.py + web/index.html; case data in casefile/ and data/2297.checks.json, regenerate with casefile/analyze.py). Reviewer pipeline in reviewer/ (python3 -m reviewer.run ...; uses headless `claude -p`), case files in data/cases/, pages /cases.html and /case.html?id=N. Log in DECISIONS.md.

Finding so far: all four AI branches carry the same unrequested change in Directory.Packages.props
(analyzer Roslyn floor 4.3.0 -> 4.12.0, PolySharp 1.14.1 -> 1.15.0). In 2297, 222 of 238 files are
generated `.g.cs` snapshots.

## Machine

- Host `pikkuinen`, Ubuntu, 4 cores, 7.6 GB RAM shared by many services; memory is tight.
  This session is capped at 2.6 GB (systemd drop-in 50-memory.conf).
- No passwordless sudo: anything needing root is a command for the user to run.
- Don't touch other projects' services (camscraper, pmarb, home automation, etc.).
- Secrets go in files with mode 600 and are never printed in chat or committed.
