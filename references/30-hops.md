# Stage 3 — Hops: from orgs, works, teams, companies to people

This is the domain-agnostic engine. Every non-person signal is converted with one of these rules.
Each produced person carries `hop_depth` (+1 per hop) and the parent signal's evidence plus the
page that named the person.

| From | Rule | Evidence to keep |
|------|------|------------------|
| `work` | Full author list via OpenAlex (`works?search=<title>`), DBLP, or OpenReview; keep authors whose institution is in region; `role` by position (first / last / coauthor). | work URL + author list page |
| `org` (lab, department, institute) | (a) Lab or group "people / team / members" page; (b) OpenAlex `authors?filter=last_known_institutions.id:<I>` restricted to the domain topic; (c) for CORDIS projects, the project website team page. | the team page URL |
| `team` (competition) | Team Description Paper or champion paper (author list via OpenAlex), team website, team GitHub organisation. Note the paper year: alumni are in it. | TDP / paper / team page URL |
| `company` | "About / team" page for founders and technical leads; OpenAlex works with the company as institution; company GitHub org; patents with company as applicant. | the specific page |
| `person` (snowball, one hop only, optional) | Co-authors in the domain with a `region_extended` affiliation in the window, via OpenAlex `works?filter=authorships.author.id:<A>,topics.id:<T>`. Mark `hop_depth: 2`, strength low. | the shared work |

Person signals retain the date of the underlying work, award, competition, or contribution;
opening a team page today does not make an old achievement recent. For snowball queries,
add `from_publication_date:<window_start>,to_publication_date:<window_end>`.
Old or undated pages may resolve identities and affiliations but cannot supply qualifying activity.

On team and people pages, copy the heading each name sits under into `role_title` ("Professors", "Doctoral
students", "Postdocs"), and emit the head of the lab or group named on the same page with the same `parent`, so stage 4
can attach the members to that group. Alumni sections go into `note`, not into member signals. Research Training
Group and IMPRS member pages follow `channels/funding-de-ch.md`.

## Budget
Hops are where pages disappear. Order: works first (cheapest, highest precision), then teams,
companies, orgs. Snowball only if the roster is below target after merging.

## Absence
If a team page or TDP cannot be found after two attempts, emit the team as a row with
`name_raw: <team name>`, `kind: team`, and `note: roster not public`. A visible gap beats a silent one.
