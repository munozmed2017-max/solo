import csv
from typing import Dict, List, Optional, Any


def track_diabetes_patients(csv_path: str = "panel.csv") -> Dict[str, Any]:
    """Finds all patients with diabetes in the panel CSV and tracks their
    visits in the last 2 years and their last A1c value.
    """
    patients: List[Dict[str, Any]] = []
    a1c_values: List[float] = []
    visits_values: List[int] = []
    uncontrolled_count = 0  # A1c >= 7.0
    missing_a1c_count = 0
    low_visit_count = 0  # visits_last_2yr < 2

    with open(csv_path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_conditions = row.get("conditions") or ""
            conditions = [c.strip() for c in raw_conditions.split(";") if c.strip()]

            has_diabetes = any("diabetes" in c.lower() for c in conditions)
            if not has_diabetes:
                continue

            raw_a1c = (row.get("last_a1c") or "").strip()
            a1c: Optional[float] = float(raw_a1c) if raw_a1c else None

            raw_visits = (row.get("visits_last_2yr") or "0").strip()
            visits = int(raw_visits) if raw_visits else 0

            if a1c is not None:
                a1c_values.append(a1c)
                if a1c >= 7.0:
                    uncontrolled_count += 1
            else:
                missing_a1c_count += 1

            if visits < 2:
                low_visit_count += 1

            visits_values.append(visits)

            patients.append({
                "id": row["id"].strip(),
                "name": row["name"].strip(),
                "age": int(row["age"]),
                "sex": row["sex"].strip(),
                "conditions": conditions,
                "last_a1c": a1c,
                "visits_last_2yr": visits,
            })

    total = len(patients)
    avg_a1c = round(sum(a1c_values) / len(a1c_values), 2) if a1c_values else None
    avg_visits = round(sum(visits_values) / len(visits_values), 2) if visits_values else 0.0

    return {
        "count": total,
        "avg_a1c": avg_a1c,
        "min_a1c": min(a1c_values) if a1c_values else None,
        "max_a1c": max(a1c_values) if a1c_values else None,
        "uncontrolled_a1c_count": uncontrolled_count,
        "controlled_a1c_count": len(a1c_values) - uncontrolled_count,
        "missing_a1c_count": missing_a1c_count,
        "avg_visits_last_2yr": avg_visits,
        "min_visits_last_2yr": min(visits_values) if visits_values else 0,
        "max_visits_last_2yr": max(visits_values) if visits_values else 0,
        "low_visit_count": low_visit_count,
        "patients": patients,
    }


if __name__ == "__main__":
    result = track_diabetes_patients("panel.csv")
    print(f"Total diabetes patients: {result['count']}")
    print(f"Average A1c: {result['avg_a1c']} (min: {result['min_a1c']}, max: {result['max_a1c']})")
    print(f"Controlled A1c (<7.0): {result['controlled_a1c_count']}, Uncontrolled (>=7.0): {result['uncontrolled_a1c_count']}, Missing A1c: {result['missing_a1c_count']}")
    print(f"Average visits (last 2 yr): {result['avg_visits_last_2yr']} (min: {result['min_visits_last_2yr']}, max: {result['max_visits_last_2yr']})")
    print(f"Patients with <2 visits in last 2 yr: {result['low_visit_count']}")
    print("\nSample tracked patients (first 5):")
    for p in result["patients"][:5]:
        print(f"  {p['id']} | {p['name']} ({p['age']}{p['sex']}) | A1c: {p['last_a1c']} | Visits (2yr): {p['visits_last_2yr']}")
