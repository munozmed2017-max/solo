"""Stubbed clinical lookup.

A fake drug-interaction database standing in for a real integration.
Agents call this directly as a plain Python helper and fold the result
into their prompt input. Swap the body for a real API call later without
touching agent code, as long as the return shape stays the same.
"""

_KNOWN_INTERACTIONS = {
    frozenset({"lisinopril", "nsaid"}): "May reduce antihypertensive effect and impair renal function.",
    frozenset({"metformin", "contrast dye"}): "Hold metformin around IV contrast studies - lactic acidosis risk.",
    frozenset({"spironolactone", "potassium"}): "Both raise serum potassium - monitor for hyperkalemia.",
}


def check_drug_interactions(meds: list[str]) -> dict:
    lowered = {m.split()[0].lower() for m in meds}
    findings = []
    for pair, warning in _KNOWN_INTERACTIONS.items():
        if pair.issubset(lowered):
            findings.append({"pair": sorted(pair), "warning": warning})
    return {"checked": sorted(lowered), "findings": findings}
