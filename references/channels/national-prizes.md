# Channel: national prizes, academies, fellowships

Universal registry in `assets/national-prizes.yaml` (prize, country, URL pattern, discipline filter).
For each prize in region whose discipline covers the domain: open the laureate page for each year
in window, emit `person` signals (`signal_type: national_prize`, strength high for senior prizes,
medium for early-career prizes which are usually the more useful ones for finding rising people).

Registry entries with `swept_by: funding-de-ch` (Emmy Noether, Heisenberg, SNSF Starting Grant, Ambizione, SNSF
Professorship) are read from the grant registers by `funding-de-ch.md`; skip them here so nobody is counted twice.
`swept_by: funding-at-se-no-dk` (FWF Wittgenstein, START, ASTRA) names an optional channel: skip the entry only when
that channel is in the run, otherwise read its laureate page here.
The Max Planck, Helmholtz, Fraunhofer and ETH early-career entries publish group leaders and fellows on programme or
institute news pages, often without a yearly list: search `"<programme>" <year>` per window year and record what was
not found in coverage.

Also include society-level recognitions filtered by European affiliation: IEEE / ACM Fellows,
ACM Doctoral Dissertation Award, Eurographics / EuroSys / ERCIM Cor Baayen awards, SIGARCH / SIGMICRO
awards, IEEE SSCS predoctoral achievement awards (circuits), RAS early-career awards (robotics).

What paid off in the 2026-10 embodied-AI run: IEEE RAS Early Career awards, the euRobotics Georges Giralt PhD award,
ELLIS programme and fellow pages, UK-RAS awards, RAEng research fellowships, NWO Vidi lists, the RAS Fellow listing
PDFs. Senior national prizes (Leibniz, Maier-Leibnitz, Latsis) had no in-domain laureate in the window: read their
full list once, record "none in domain", move on. ELLIS expert lists beyond page 1 are JS-rendered and unreadable.

Traps: laureate pages list affiliation at award time; some prizes name a team, which is a `team` signal for the hop.

## role_title and topics
- `role_title`: the position line printed with the laureate ("Junior Professor", "Research Group Leader"); without
  one, the prefix as printed ("Prof. Dr.").
- `topics`: from the title of the awarded work or project named on the page; leave empty when the page names only
  a field.
