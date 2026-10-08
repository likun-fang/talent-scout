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
