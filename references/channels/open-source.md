# Channel: open source

GitHub anonymous REST API (60 requests/hour, no key):
- Repo anchors from the domain map → `GET /repos/{owner}/{repo}/contributors?per_page=100`.
- For top contributors → `GET /users/{login}` for `location`, `company`, `blog`, `name`. Region match on `location` is fuzzy (city names, country names in local languages); record the raw string.
- Organisation members are public only if the member made them public.

Emit `person` signals with `role: maintainer` (owner / top 3 contributors) or `coauthor` (others),
strength low unless the repo is the domain's reference implementation. Hugging Face model / dataset
authors and foundation project rosters (e.g., ROS, LLVM, RISC-V tooling) follow the same pattern.
