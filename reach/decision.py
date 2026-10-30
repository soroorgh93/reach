"""Decision layer: Evidence x Reachability x Engagement, adjudicated across stakeholders.

Three stakeholders weigh the axes differently (the person, their carer, the clinician).
Reach computes each intervention's utility under every stance, then reports:
  * Bayes: the average-case choice (equal prior over stances);
  * minimax: the choice whose worst stance is least bad;
  * least-favourable prior: multiplicative-weights boosting over the stances converges to
    the prior under which Bayes = minimax, and the resulting weights say which stakeholder
    the recommendation must satisfy to be robust.
Evidence effect sizes from several sources are pooled with BLUE (inverse-variance) weights.
A policy gate, borrowed from EdgeGuardian, decides whether recommending is justified:
    justified <=> p >= threshold and p * benefit >= (1 - p) * cost.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

GRADE_BASE = {"A": 0.95, "B": 0.75, "C": 0.45, "D": 0.2, "X": 0.0}
GRADE_SE = {"A": 0.05, "B": 0.10, "C": 0.20, "D": 0.30, "X": 1.0}

STANCES = {
    "person":    {"evidence": 0.25, "reachability": 0.35, "engagement": 0.40},
    "carer":     {"evidence": 0.35, "reachability": 0.45, "engagement": 0.20},
    "clinician": {"evidence": 0.55, "reachability": 0.30, "engagement": 0.15},
}
CHANNEL_COST = {"auditory": 0.10, "visual": 0.12, "audiovisual": 0.14, "tactile": 0.08, "environment": 0.15,
                "activity": 0.20, "visual_text": 0.12, "clinic": 0.45, "prescription": 0.35, "none": 1.0}


def blue_pool(effects: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Best linear unbiased estimate: inverse-variance weighted mean of (effect, se)."""
    pairs = [(e, s) for e, s in effects if s and s > 0]
    if not pairs:
        return None
    w = np.array([1.0 / s ** 2 for _, s in pairs])
    e = np.array([e for e, _ in pairs])
    return float((w * e).sum() / w.sum()), float(math.sqrt(1.0 / w.sum()))


def evidence_score(iv: dict[str, Any]) -> dict[str, Any]:
    grade = iv.get("grade", "D")
    base = GRADE_BASE.get(grade, 0.2)
    eff = iv.get("effect")
    ci = iv.get("effect_ci")
    pooled = None
    if eff is not None and ci:
        se = max((ci[1] - ci[0]) / 3.92, 0.02)
        # pool the registry estimate with a sceptical prior centred on a small effect (0.2)
        pooled = blue_pool([(float(eff), se), (0.2, 0.35)])
    if pooled:
        e_hat, se_hat = pooled
        strength = 1.0 / (1.0 + math.exp(-(e_hat - 0.3) / 0.15))     # 0.3 = small-to-moderate
        score = 0.6 * base + 0.4 * strength
        return {"score": round(score, 3), "grade": grade, "pooled_effect": round(e_hat, 3),
                "pooled_se": round(se_hat, 3), "n": iv.get("n")}
    return {"score": round(base * 0.85 if grade != "X" else 0.0, 3), "grade": grade, "pooled_effect": None,
            "pooled_se": None, "n": iv.get("n")}


def utility(e: float, r: float, g: float, w: dict[str, float]) -> float:
    """Weighted geometric mean: a zero on any axis is a zero overall (a REFUSE cannot be bought back)."""
    if min(e, r, g) <= 0:
        return 0.0
    return math.exp(w["evidence"] * math.log(e) + w["reachability"] * math.log(r) + w["engagement"] * math.log(g))


def adjudicate(rows: list[dict[str, Any]], eta: float = 0.5, rounds: int = 300) -> dict[str, Any]:
    """rows: [{id, evidence, reachability, engagement}] -> ranking under Bayes, minimax, LFP."""
    ids = [r["id"] for r in rows]
    stances = list(STANCES)
    U = np.array([[utility(r["evidence"], r["reachability"], r["engagement"], STANCES[s]) for r in rows] for s in stances])
    n = len(ids)
    if n == 0:
        return {"ranking": [], "weights": {}, "bayes": None, "minimax": None, "lfp": None}
    # per-stance percentile rank so stances are comparable
    R = np.argsort(np.argsort(U, axis=1), axis=1) / max(n - 1, 1)
    bayes = R.mean(axis=0)
    worst = R.min(axis=0)
    # multiplicative weights over stances: nature picks the stance that hurts the current favourite
    w = np.ones(len(stances)) / len(stances)
    counts = np.zeros(n)
    for _ in range(rounds):
        i = int(np.argmax(w @ R))
        counts[i] += 1
        w = w * np.exp(-eta * R[:, i])
        w = w / w.sum()
    lfp_value = w @ R
    mixed = counts / counts.sum()
    final = 0.5 * lfp_value + 0.3 * bayes + 0.2 * worst
    order = np.argsort(-final)
    ranking = []
    for k in order:
        ranking.append({"id": ids[k], "final": round(float(final[k]), 4), "bayes": round(float(bayes[k]), 3),
                        "worst_case": round(float(worst[k]), 3), "lfp": round(float(lfp_value[k]), 3),
                        "play_share": round(float(mixed[k]), 3),
                        "utility": {s: round(float(U[j, k]), 3) for j, s in enumerate(stances)}})
    return {"ranking": ranking, "weights": {s: round(float(w[j]), 3) for j, s in enumerate(stances)},
            "bayes": ids[int(np.argmax(bayes))], "minimax": ids[int(np.argmax(worst))],
            "lfp": ids[int(np.argmax(lfp_value))]}


def policy_gate(p: float, channel: str, grade: str, threshold: float = 0.5) -> dict[str, Any]:
    cost = CHANNEL_COST.get(channel, 0.3)
    benefit = {"A": 1.0, "B": 0.8, "C": 0.5, "D": 0.3, "X": 0.0}.get(grade, 0.3)
    justified = p >= threshold and p * benefit >= (1 - p) * cost
    return {"p": round(p, 3), "cost": cost, "benefit": benefit, "threshold": threshold, "justified": bool(justified),
            "rule": "p >= threshold and p*benefit >= (1-p)*cost"}


def belief(final_rank_value: float, evidence: float, support: float = 0.0, w: float = 0.5) -> float:
    """EdgeGuardian belief update: sigmoid(logit(p) + 2*w*support)."""
    p0 = min(max(0.5 * final_rank_value + 0.5 * evidence, 1e-3), 1 - 1e-3)
    z = math.log(p0 / (1 - p0)) + 2 * w * support
    return 1.0 / (1.0 + math.exp(-z))


def group_adjudicate(U: "np.ndarray", ids: list[str], members: list[str], eta: float = 0.5, rounds: int = 400) -> dict[str, Any]:
    """U[m, i] = how much member m gets from option i (0..1). Returns Bayes (average), minimax (worst member),
    and the least-favourable prior over members found by multiplicative weights, with the mixed strategy."""
    U = np.asarray(U, dtype=float)
    m, n = U.shape
    if n == 0 or m == 0:
        return {"ranking": [], "weights": {}, "bayes": None, "minimax": None, "lfp": None}
    R = np.argsort(np.argsort(U, axis=1), axis=1) / max(n - 1, 1) if n > 1 else np.ones_like(U)
    bayes = R.mean(axis=0); worst = R.min(axis=0)
    w = np.ones(m) / m; counts = np.zeros(n)
    for _ in range(rounds):
        i = int(np.argmax(w @ R)); counts[i] += 1
        w = w * np.exp(-eta * R[:, i]); w = w / w.sum()
    lfp = w @ R
    final = 0.5 * lfp + 0.3 * bayes + 0.2 * worst
    order = np.argsort(-final)
    ranking = [{"id": ids[k], "final": round(float(final[k]), 4), "bayes": round(float(bayes[k]), 3), "worst": round(float(worst[k]), 3),
                "lfp": round(float(lfp[k]), 3), "per_member": {members[j]: round(float(U[j, k]), 3) for j in range(m)}} for k in order]
    return {"ranking": ranking, "weights": {members[j]: round(float(w[j]), 3) for j in range(m)},
            "bayes": ids[int(np.argmax(bayes))], "minimax": ids[int(np.argmax(worst))], "lfp": ids[int(np.argmax(lfp))]}
