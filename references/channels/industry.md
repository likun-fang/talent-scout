# Channel: industry labs and competitor companies

Only public professional artefacts:
- Papers with company affiliation in region (OpenAlex institutions of type `company`, or user-named companies → `authorships.institutions.id`).
- Patents: Espacenet / Google Patents, applicant = company, inventor address in region; emit `person` with `role: inventor`, strength medium.
- Public talks: conference programmes, meetup pages, company engineering blogs with bylines.
- Open source: company GitHub organisations (see `open-source.md`).

No social-network scraping, no login-gated pages. If the user names competitors, add them to the
domain map `companies:` list with the reason.
