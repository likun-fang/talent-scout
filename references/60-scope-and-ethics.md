# Scope and conduct (read once per run)

- Purpose is discovery of technology and research groups through people's **public professional record**. Output
  lists people and their work; it does not assess willingness to move, salary, seniority fit, or
  anything about private life.
- Role class and group are data taken from public pages; they are not an assessment of anyone.
- Sources are the public professional record: institutional web pages, papers, grant registers, competition
  results, public code, company team pages. LinkedIn is not read at any stage, not even to confirm a role;
  `group_export.py`, `check_groups.py` and `publish_site.py` refuse any LinkedIn key or URL. Login-gated content,
  social-network profiles, people-search aggregators and private contact details stay outside the run.
- Record no sensitive categories (health, politics, religion, ethnicity, nationality beyond what
  an affiliation country implies).
- Every stored fact carries its public URL so the subject's own public record can be re-checked.
- A published map links a correction form and a removal form. A removal request needs no reason and is honoured at
  the next publication: the person, or the whole group when its PI asks, is left out of that field's map. The
  requests are kept outside the repository (`50-output.md`); the public issue is the person's own record of it.
- Exclude junior / school-level competitions and anyone evidently a minor.
- Keep `run.meta.json` with the run; it states purpose, date, scope, window and sources, which is the
  minimum a data controller needs to document processing of public data under legitimate interest. Page records
  from the final pass live in the run directory with the table and are deleted with it.
