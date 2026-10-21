"""
Write H1, B1, H2, B2 for each local scenario.

Reads testbed/scenarios.py only. Does not contact a network and does not score pages.
"""

import csv
from pathlib import Path

from scenarios import SCENARIOS, dynamic_page

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "captures"
ORDER = ("H1", "B1", "H2", "B2")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, spec in SCENARIOS.items():
        for index, view in enumerate(ORDER, start=1):
            profile = "human" if view.startswith("H") else "bot"
            if name == "legitimate_dynamic":
                html = dynamic_page(f"{view}-{index}")
            else:
                html = spec[profile]
            path = OUT / f"{name}_{view}.html"
            path.write_text(html, encoding="utf-8")
            rows.append({
                "scenario": name,
                "known_behavior": spec["known_behavior"],
                "view_id": view,
                "profile": profile,
                "artifact": str(path.relative_to(ROOT.parent)).replace("\\", "/"),
                "ground_truth_source": "scenario configuration in testbed/scenarios.py",
                "real_world_incident": "no",
            })
    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} local views")


if __name__ == "__main__":
    main()
