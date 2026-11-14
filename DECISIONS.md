# Decision and lessons log

## 2026-11-14

- **Demo change: ju26-issue-2297.** 238 files, 222 of them generated snapshots. It shows the clearest drop from "files changed" to "decisions a human must make".
- **The reviewer never approves.** It sorts the change into proven / supported / contested / refused / not checked. Only a named owner signs.
- **Proof first, model second.** Snapshot shape, template pairs and attribute availability are deterministic checks with a re-run command. The model only explains what is left.
- **Refusal policy P4:** dependency and toolchain floors are product decisions. The reviewer describes the blast radius and does not judge it.
- **A sign-off binds to commit + evidence hash.** If either changes, the server rejects the signature (HTTP 409).
- **Requirement IDs are placeholders** (REQ-2297.x, written from the upstream issue) until we receive Tieto's requirements set.

## Failure modes seen

- **Agent tests confirm the agent's own wrong belief.** The guard test passes with the bug and would fail on the fix. Lesson: tests written by the author are claims too.
- **Wrong reasoning leaks into the docs.** The README tells users the attribute "is not available" on netstandard2.0 / .NET Framework, which the reference assemblies disprove.
- **Environment drift spreads across changes.** The same Directory.Packages.props hunk appears in all four agent branches.
- **The reviewer can be wrong too.** Each finding states what would make it wrong (F1: a consumer polyfill clash; not compiled).

## 2026-11-14, reviewer pipeline

- **Pipeline order: deterministic proofs → policy gate → one AI call → quote verifier → rule-based routing.** The AI sees only what the machine could not prove. Policy-gated files are shown to it but marked "do not judge".
- **Quote-or-drop.** Every AI finding must quote exact diff lines from a named file, or it is deleted before a human sees it. 0 of 22 findings were dropped on the first full run.
- **Routing uses named rules, not a score.** Policy hit → owner. High severity, or medium defect / false claim / unrequested change with an owner question → owner. Everything else is handled.
- **Reviewer backend:** headless Claude CLI with no tools and JSON-schema output. About 30–45 s per change.
- **Public-API rule excludes generator and analyzer projects** (repo config). Their `public` types are not shipped to users.

## Failure modes seen (reviewer)

- **Run-to-run variance.** On 2297 the first run raised a duplicate-attribute risk (CS0579) that the second run did not. Severity also shifted, which changed the decision count from 3 to 2. To measure next.
- **The AI found the false premise on its own** but cannot prove it without a tool; the machine probe (reference-assembly check) supplies the proof.
