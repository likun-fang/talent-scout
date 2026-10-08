# Channel: industry labs and competitor companies

OpenAlex traps for companies: multinationals are often filed under one national record ("Google DeepMind (United
Kingdom)", "Nvidia (United Kingdom)") so US staff appear as GB; several European labs have no institution record
(NAVER LABS Europe, Bosch Center for AI, Meta FAIR Paris, Huawei Noah's Ark London, Hugging Face Paris). Query
`raw_affiliation_strings.search:<company> <city>` and reject strings naming a US city; add a title keyword filter when
the topic is noisy. arXiv-only papers usually carry no affiliation at all.

Only public professional artefacts:
- Papers with company affiliation in region (OpenAlex institutions of type `company`, or user-named companies → `authorships.institutions.id`).
- Patents: Espacenet / Google Patents, applicant = company, inventor address in region; emit `person` with `role: inventor`, strength medium.
- Public talks: conference programmes, meetup pages, company engineering blogs with bylines.
- Open source: company GitHub organisations (see `open-source.md`).

No social-network scraping, no login-gated pages. If the user names competitors, add them to the
domain map `companies:` list with the reason.
