# Channel: national prizes, academies, fellowships

Universal registry in `assets/national-prizes.yaml` (prize, country, URL pattern, discipline filter).
For each prize in region whose discipline covers the domain: open the laureate page for each year
in window, emit `person` signals (`signal_type: national_prize`, strength high for senior prizes,
medium for early-career prizes which are usually the more useful ones for finding rising people).

Also include society-level recognitions filtered by European affiliation: IEEE / ACM Fellows,
ACM Doctoral Dissertation Award, Eurographics / EuroSys / ERCIM Cor Baayen awards, SIGARCH / SIGMICRO
awards, IEEE SSCS predoctoral achievement awards (circuits), RAS early-career awards (robotics).

Traps: laureate pages list affiliation at award time; some prizes name a team, which is a `team`
signal for stage 3.
