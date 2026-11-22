"""What the panel shows: campaigns with their families and explanations, and one case flattened for a card."""
from collections import Counter
from itertools import combinations
from typing import Any, Dict, List

from .. import clustering, database, decision, explain
from ..urls import host, reg_domain
from .index import campaigns, pair_table


def groups_overview(profiles: Dict[str, dict], tau: float) -> List[Dict[str, Any]]:
    """Campaigns at tau, largest family first; each with its family number, members, the evidence that links them
    and its explanation (explain.campaign)."""
    scores = pair_table(profiles)
    groups = campaigns(profiles, tau)
    out = []
    for fam_no, family in enumerate(clustering.hierarchy(profiles, groups, decision.FAMILY_SCORE, scores), 1):
        for ci in family:
            members = groups[ci]
            links = [{"a": a, "b": b, "score": clustering.pair(scores, a, b)["score"],
                      "evidence": clustering.pair(scores, a, b)["strong_links"]} for a, b in combinations(members, 2)]
            scam = Counter(profiles[c]["core_narrative"]["ad_goal_scam_type"] for c in members).most_common(1)[0][0]
            out.append({"family": fam_no, "members": members, "scam_type": scam,
                        "links": sorted(links, key=lambda x: -x["score"]),
                        "explanation": explain.campaign(members, profiles, scores, tau, groups)})
    return out


def case_summary(cid: str, p: Dict[str, Any]) -> Dict[str, Any]:
    """What an analyst wants to see about one case, flattened from its profile and case_input."""
    n, e, v, ta = p["core_narrative"], p["entities"], p["visual_and_production"], p["technical_artifacts"]
    urls = (ta.get("redirect_chain") or []) + (ta.get("urls_and_domains") or [])
    return {
        "case": cid, "scam_type": n["ad_goal_scam_type"], "topic": n["topic"],
        "product": e["product_or_platform"].get("exact_name") or e["product_or_platform"].get("generic_category"),
        "people": [x.get("name") or f"unnamed {x.get('category_or_role')}" for x in e["featured_people"]],
        "media": e["impersonated_media"], "companies": e["companies_or_institutions"],
        "templates": f"{v['ad_creative_template'] or 'no ad'} -> {v['landing_page_template'] or 'no page'}",
        "persuasion": n["persuasion_devices"], "summary": p["canonical_comparison_text"],
        "domains": sorted({reg_domain(host(u)) for u in urls if host(u)}), "trackers": ta.get("tracker_ids") or [],
        "infra": [f for f in ta.get("domain_and_cert_metadata") or [] if not f.startswith(("domain:", "regbatch:"))],
        "image": database.first_image(cid),
    }
