"""Stubbed clinical/admin lookups.

These are fake data sources standing in for real integrations (pharmacy
formulary APIs, drug interaction databases, payer portals). Agents call
these directly as plain Python helpers and fold the results into their
prompt input. Swap the bodies for real API calls later without touching
agent code, as long as the return shape stays the same.
"""

_KNOWN_INTERACTIONS = {
    frozenset({"lisinopril", "nsaid"}): "May reduce antihypertensive effect and impair renal function.",
    frozenset({"metformin", "contrast dye"}): "Hold metformin around IV contrast studies - lactic acidosis risk.",
}


def check_drug_interactions(meds: list[str]) -> dict:
    lowered = {m.split()[0].lower() for m in meds}
    findings = []
    for pair, warning in _KNOWN_INTERACTIONS.items():
        if pair.issubset(lowered):
            findings.append({"pair": sorted(pair), "warning": warning})
    return {"checked": sorted(lowered), "findings": findings}


def check_insurance_formulary(insurer: str, medication: str) -> dict:
    tier = (hash(f"{insurer}:{medication.lower()}") % 4) + 1
    return {
        "insurer": insurer,
        "medication": medication,
        "covered": tier < 4,
        "tier": tier,
        "prior_auth_required": tier >= 3,
    }


def schedule_followup(reason: str, days_out: int = 14) -> dict:
    return {
        "reason": reason,
        "suggested_in_days": days_out,
        "note": "Stub scheduler - wire up to a real calendar later.",
    }
