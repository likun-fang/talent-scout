# Channel: startups

Sources (keyless): EIC Accelerator selected-company PDFs; EIC Pathfinder / Transition lists;
national programme lists (e.g., EXIST, i-Nov, Innovate UK, Innosuisse) when the user asks; press
lists for the domain (search `<domain> startup raises <year> Europe`); OpenAlex institutions of
type `company` publishing in the domain.

Company team pages mostly name no CTO or researchers; founders come from press releases and funding news, sometimes
by first name only. Attach an OpenAlex id to a founder only when the profile's topics match the domain. Leave out
companies whose European HQ is not stated.

Emit `company` signals with country and the evidence URL. Founders and technical leads are resolved
in stage 3 from the company's own team page, its publications, and its GitHub organisation.
Do not use paid databases unless the user supplies access.
