Continue building Tasklane (repo avishekdas/sundaydotcom; my local copy ~/tasklane on this Mac — work, commit and
push directly there; you own git push).

1. Read CLAUDE.md first — it is the hand-off from the previous session (rules, environment, learnings, exact status
   and next steps). Then follow its start-of-session checklist before changing anything: the plan's M1 section,
   the decision-log tail (D-045…D-058), the M0b review, the requirement files for the next story; baseline the
   gates; check CI.
2. Before pushing anything, check the pipeline: do not push while a `ci` run is in progress, and prefer waiting
   for deploy-dev to finish.
3. First task: dev was green on 2dbfe0a at hand-off (Tier B incl. the AC-K7-2 two-IP check). Check the latest
   ci / deploy-dev / e2e-dev runs and the first `nightly` run; if anything is red, read the check-run annotations,
   find the cause and fix it test-first (red pushed alone, then green).
4. Then close M1 per plan §1.3: system-test report docs/04-plan/system-tests/M1.md, plan status line, and an
   independent review agent writing docs/04-plan/milestone-reviews/M1.md; fix blocking findings; ask me to
   approve. After that, start M2.
5. Before every story and every step: restate it, its acceptance criteria and the north-star steps it moves, and
   ask me questions ONE AT A TIME (plain text, lettered options, recommended first, with enough context) until you
   are at least 95% confident. Decisions with cost or external effect are mine; record them as D-xxx.
6. Tests first: commit and push the failing test on its own and let CI record the red run, then the fix.
   Milestones end with their north-star steps passing on Tier A and Tier B plus an independent review.
7. Keep CLAUDE.md current as you learn things (status after every story, gotchas as they happen).
