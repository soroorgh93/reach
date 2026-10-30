"""Reachability rules: can this intervention physically and practically reach this person?

Every rule has a stable id, returns PASS, REVIEW or REFUSE with a one-line reason, and
is deterministic. A REFUSE is never softened by taste or evidence downstream; it is
shown struck through with the rule id, so a clinician can see exactly why.
Scores: PASS 1.0, REVIEW 0.55, REFUSE 0.0; the reachability factor is the product.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

PASS, REVIEW, REFUSE = "PASS", "REVIEW", "REFUSE"
WEIGHT = {PASS: 1.0, REVIEW: 0.55, REFUSE: 0.0}

PROVIDER_CATEGORY = {
    "neuromodulation_clinic": "urn:tag:category:place:psychiatrist",
    "physician": "urn:tag:category:place:doctor",
    "oncology": "urn:tag:category:place:oncologist",
    "genetic_counselling": "urn:tag:category:place:medical_clinic",
    "speech_pathologist": "urn:tag:category:place:speech_pathologist",
    "audiologist": "urn:tag:category:place:audiologist",
    "occupational_therapist": "urn:tag:category:place:occupational_therapist",
}


@dataclass
class RuleResult:
    rule: str
    verdict: str
    reason: str

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def _cap(profile: dict[str, Any], name: str, default: str = "full") -> str:
    return str(profile.get("capacities", {}).get(name, default)).lower()


def evaluate(intervention: dict[str, Any], profile: dict[str, Any], providers_nearby: int | None = None) -> dict[str, Any]:
    req = intervention.get("requires", {}) or {}
    flags = {f.lower() for f in profile.get("flags", [])}
    age = profile.get("age")
    results: list[RuleResult] = []

    # R-SENS-AUD: auditory channel needs hearing.
    if req.get("hearing"):
        h = _cap(profile, "hearing")
        if h in ("none", "deaf"):
            results.append(RuleResult("R-SENS-AUD", REFUSE, "auditory delivery; the person does not hear"))
        elif h in ("partial", "hard_of_hearing", "aided"):
            results.append(RuleResult("R-SENS-AUD", REVIEW, "auditory delivery with partial hearing; check with an audiologist"))
        else:
            results.append(RuleResult("R-SENS-AUD", PASS, "hearing is sufficient for auditory delivery"))

    # R-SENS-VIS: visual channel needs vision; text channel needs reading.
    if req.get("vision"):
        v = _cap(profile, "vision")
        if v in ("none", "blind"):
            results.append(RuleResult("R-SENS-VIS", REFUSE, "visual delivery; the person does not see"))
        elif v in ("partial", "low"):
            results.append(RuleResult("R-SENS-VIS", REVIEW, "visual delivery with low vision"))
        else:
            results.append(RuleResult("R-SENS-VIS", PASS, "vision is sufficient"))
    if req.get("reading"):
        r = _cap(profile, "reading", "yes")
        if r in ("no", "none", "false"):
            results.append(RuleResult("R-VERBAL", REFUSE, "text-based delivery; the person does not read"))
        elif r in ("emerging", "supported"):
            results.append(RuleResult("R-VERBAL", REVIEW, "text-based delivery; reading is supported, not independent"))
        else:
            results.append(RuleResult("R-VERBAL", PASS, "reads independently"))

    # R-AGE
    if req.get("min_age") is not None and age is not None:
        if age < req["min_age"]:
            results.append(RuleResult("R-AGE", REFUSE, f"minimum age {req['min_age']}; the person is {age}"))
        else:
            results.append(RuleResult("R-AGE", PASS, f"age {age} meets the minimum of {req['min_age']}"))

    # R-MOTOR
    if req.get("mobility") == "ambulatory":
        m = _cap(profile, "mobility", "ambulatory")
        if m in ("wheelchair", "bedbound", "none"):
            results.append(RuleResult("R-MOTOR", REFUSE, "requires walking or standing; the person uses a wheelchair"))
        elif m in ("limited", "assisted"):
            results.append(RuleResult("R-MOTOR", REVIEW, "requires movement; mobility is limited"))
        else:
            results.append(RuleResult("R-MOTOR", PASS, "mobility is sufficient"))

    # R-SAFETY: contraindications declared on the person.
    for c in intervention.get("contraindications", []) or []:
        if c.lower() in flags:
            results.append(RuleResult("R-SAFETY", REFUSE, f"contraindicated: {c.replace('_', ' ')}"))
    if not any(r.rule == "R-SAFETY" for r in results) and intervention.get("contraindications"):
        results.append(RuleResult("R-SAFETY", PASS, "no declared contraindication applies"))

    # R-PROVIDER: clinic-delivered interventions need a provider within reach.
    if req.get("provider"):
        if providers_nearby is None:
            results.append(RuleResult("R-PROVIDER", REVIEW, f"needs a {req['provider'].replace('_', ' ')}; provider lookup unavailable"))
        elif providers_nearby == 0:
            results.append(RuleResult("R-PROVIDER", REVIEW, f"no {req['provider'].replace('_', ' ')} found near {profile.get('city', 'the person')}"))
        else:
            results.append(RuleResult("R-PROVIDER", PASS, f"{providers_nearby} {req['provider'].replace('_', ' ')} option(s) near {profile.get('city', 'the person')}"))

    # R-GENOME
    if req.get("genome"):
        if profile.get("genome"):
            results.append(RuleResult("R-GENOME", PASS, "genomic data available"))
        else:
            results.append(RuleResult("R-GENOME", REFUSE, "requires tumour or germline sequencing; none on file"))

    # R-CONSENT: taste personalisation requires consent to use favourites.
    if intervention.get("engagement_domain") and not profile.get("consent", {}).get("taste", True):
        results.append(RuleResult("R-CONSENT", REVIEW, "person has not consented to taste personalisation; engagement scored as unknown"))

    # R-SCOPE: excluded items never reach.
    if intervention.get("grade") == "X":
        results.append(RuleResult("R-SCOPE", REFUSE, "not a clinical intervention"))

    # R-ONLINE: home-deliverable items need a device; clinic items need travel.
    if intervention.get("home_deliverable") and _cap(profile, "device", "yes") in ("no", "none"):
        results.append(RuleResult("R-ONLINE", REVIEW, "home delivery needs a device the household does not have"))

    score = 1.0
    for r in results:
        score *= WEIGHT[r.verdict]
    verdict = REFUSE if any(r.verdict == REFUSE for r in results) else (REVIEW if any(r.verdict == REVIEW for r in results) else PASS)
    return {"score": round(score, 3), "verdict": verdict, "rules": [r.dict() for r in results]}
