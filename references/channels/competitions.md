# Channel: competitions and challenges

Competitions name **teams**, rarely people. Sweep emits `team` signals; stage 3 turns them into people.

## Procedure
- For each competition in the domain map × year: results page → ranked teams with institution and country. Emit a `team` signal for each team in region in the top N (default N = 5) and for any team that won a technical / innovation award.
- Record where the roster will come from: RoboCup leagues require a Team Description Paper (TDP) per team per year, usually linked from the league site or the team site; conference challenges (ICRA/IROS/NeurIPS) often link a team paper or repo; Kaggle / Codeforces style leaderboards give handles.
- Also capture competition "best paper" or "open research challenge" winners as `work` signals.

## Traps
- Winners are often non-European; filter at team level before spending pages.
- A TDP lists everyone including alumni; keep all with `role: team_member`, let the table show hop depth 1.
- Student competitions can include minors (RoboCupJunior, IOI). Exclude junior / school leagues.
