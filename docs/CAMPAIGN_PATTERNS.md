# Campaign patterns found in the sample cases

Abstract patterns only: the sample material may not be redistributed, so this file names no domains, people, products,
tracker IDs or page titles. Numbers are from the 10 sample cases (`python -m ads.evaluation.features`, `ads.evaluation.evaluate`,
`ads.evaluation.quality`, `ads.explain --campaigns`, and the facts written by `python -m ads.preprocess.enrich --domain-meta`).

## Infrastructure
1. **Fresh domains.** Three of the seven captured domains were one day old when the ad was recorded; the others were
   39 to 288 days old. A domain registered the day before the ad ran is a strong sign of a campaign domain.
2. **Batch registration.** The two domains of one gold campaign were registered on the same day at the same budget
   registrar. Registration batches link campaign domains even when everything else on the page changes.
3. **CDN fronting.** Six of eight domains use the same CDN for name servers and hosting. Network-level traces (IP,
   hosting network, `server` header) therefore cannot separate operators; application-level traces must.
4. **Shared landing-page tooling.** One scheme family shares the same platform endpoint paths (session recording and
   form submission APIs) and the same non-standard set of tracking parameters across domains and campaigns: one tool,
   several campaigns. This is family-level evidence, not proof of one operator.
5. **Ad platform IDs in links.** Health-scheme funnels carry long ad campaign IDs in the tracking parameters; one ID
   shared by two cases would identify one advertising campaign.
6. **Already known.** Two of seven captured domains were already on the CERT Polska warning list.

## Pages
7. **Page kits.** Pages of one campaign reuse the same images (identical files) and the same HTML skeleton (tag paths,
   CSS classes) on different domains. Image kits and skeletons also cross campaign boundaries inside one scheme: one
   recorded funnel contains a page built from another campaign's kit, which is why a shared kit links a family, not a
   campaign.
8. **Fake news article as the bridge page.** The investment scheme uses an article template impersonating a news
   outlet, with a fabricated story about a public figure, comments and a live or breaking label; the offer page is a
   registration form with a call from an "advisor".
9. **Cloaking and runtime injection.** Some pages show little text without JavaScript, and tracking pixels can be
   injected only at runtime: recorded network logs see more than a static fetch.

## Content
10. **Surface swaps on a fixed template.** Campaigns keep the template, the persuasion devices and the call to action
    and swap the person, the product name, the outlet and the amounts. Across the investment family, scam type, landing
    template and call to action stay the same (AUC 1.00), while people and products differ between campaigns.
11. **Universal persuasion.** Celebrity endorsement, fake comments, testimonials, time-limited offers and fake media
    branding appear across unrelated schemes: they describe the genre, and on their own they mislead (7 false hits on
    32 unrelated pairs for persuasion devices, 16 for funnel stages).
12. **Ad creative templates vary inside a campaign.** The same campaign uses different creative formats (breaking news,
    incident footage, report), so the ad template does not separate campaigns (AUC 0.44); the landing page does.
13. **Video-only health ads.** The health scheme arrives as video ads with no captured landing infrastructure; they are
    linked by content into a family, never into a campaign, which is the honest level for content-only evidence.

## Consequences for detection
- Look for operators in application traces (trackers, endpoints, tracking templates, page kits, registration batches)
  and for schemes in content (scam type, landing template, call to action).
- Treat a page kit or a landing-page tool as a family link: several operators share them.
- Capture the network log: it holds the traces a static fetch misses, and domains die within weeks.
