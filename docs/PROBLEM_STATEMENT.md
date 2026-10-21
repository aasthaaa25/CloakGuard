# Problem statement

CloakGuard is not the answer to a numbered USENIX or NDSS contest problem. No such problem statement is attached to this repository. The work sits next to three published lines of research:

1. **Split-view cloaking detection.** Invernizzi et al., “Cloak of Visibility: Detecting When Machines Browse a Different Web” (IEEE S&P 2016), compare what different browsing profiles receive. Wang et al., “Cloaker Catcher” (2017), compare a user’s view with a crawler view. Dual-view comparison itself is prior work.
2. **Promotional defacement detection.** Yang et al., “Scalable Detection of Promotional Website Defacements in Black Hat SEO Campaigns” (USENIX Security 2021), detect injected promotional content, including obfuscated jargon, on compromised sites. That paper does not require a split view.
3. **Owner-side response.** A site operator can monitor requests to infrastructure they control. That is a different problem from identifying the person who altered a remote server.

The scoped question for this repository is:

> Given paired fetches of the same URL under two declared client profiles, which differences are worth retaining as evidence, which scores are only heuristics, and which actions are legitimate for the owner of the monitored site?

Success on URL-string classification does not answer that question. A User-Agent set to `Googlebot` is not traffic from Google’s infrastructure.
