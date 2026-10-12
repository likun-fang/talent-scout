# Channel: open source

From agent sandboxes the GitHub REST API, `gh api` and the `/graphs/contributors` page are usually blocked (403 /
robots). What works without budget: `git clone --bare --filter=blob:none https://github.com/<o>/<r>` then
`git log --no-merges --since=<year> --format='%aN|%aE' | sort | uniq -c` for per-person commits, email domains as
region hints, and `git show HEAD:CITATION.cff` / `CONTRIBUTORS.md` / `package.xml` for maintainers and affiliations.
Region comes from the GitHub profile page (location, company); when blank, from OpenAlex or the commit email domain,
and the record's note says which. Maintainers often move to startups; the profile is current only as of its last edit.

When the REST API is reachable (60 requests/hour, no key):
- Repo anchors from the domain map → `GET /repos/{owner}/{repo}/contributors?per_page=100`.
- For top contributors → `GET /users/{login}` for `location`, `company`, `blog`, `name`. Region match on `location` is fuzzy (city names, country names in local languages); record the raw string.
- Organisation members are public only if the member made them public.

Emit `person` signals with `role: maintainer` (owner / top 3 contributors) or `coauthor` (others),
strength low unless the repo is the domain's reference implementation. Hugging Face model / dataset
authors and foundation project rosters (e.g., ROS, LLVM, RISC-V tooling) follow the same pattern.

## Optional model-card and technical-report hops

Run this expanded procedure only when `run.meta.json.sourcing_extensions.model_cards` is explicitly `true`.
The existing repository sweep and its budget remain unchanged; use the remaining budget for these anchors,
including failed fetch attempts. Record skipped anchors and blocked/private pages in channel coverage.

1. Read each relevant public model/dataset card from the domain map, recording its canonical URL and links to
   the original technical report, code repository and credited contributors. A model owner organisation or an
   uploader handle is a lead, not proof of a natural person or authorship. Mirrors, quantizations and fine-tunes
   do not establish participation in the original model; distinguish their own attributable contributions.
2. Follow the linked report's complete author list, explicit credits, or repository contribution history to
   named people. Use the existing work-to-person hop and identity keys. A report can be a `work` signal with
   `signal_type: paper`; a named, evidenced model contributor can use `signal_type: model_contribution` and
   `role: coauthor` or `maintainer` only as supported by the source. Use `unknown` if a precise role is unresolved.
   Keep these signals in `channel: open-source`, with source URL, `parent` and normal hop-depth limits.
3. Verify each person's regional affiliation from attributable public professional evidence. Do not apply a
   global organisation's headquarters country to every author. If the person's region cannot be established,
   record the unresolved lead in coverage rather than inventing a country or emitting an in-region person.
4. Date person signals by an attributable contribution/release or the report publication, within the run
   window. A recent card edit, download count, trending rank or crawl date does not date a person's work.
   Undated credits remain background. Use `medium` for directly documented domain-relevant work/contributions,
   `low` for uncertain attribution with the caveat retained; popularity alone never increases strength.

Reuse DOI/work IDs and public person IDs so reports rediscovered by other channels merge normally; preserve both
evidence records without claiming independent projects. Copy job titles only when explicitly associated with the
person, and copy topics from the model/report/repository text under the existing topic rules.

## role_title and topics
- `role_title`: the heading the name sits under in `CONTRIBUTORS.md`, `MAINTAINERS` or the README ("Maintainers",
  "Core developers"); `CITATION.cff` and commit logs carry none.
- `topics`: the repository name, plus a phrase from the title of the paper the repository cites, if any.
