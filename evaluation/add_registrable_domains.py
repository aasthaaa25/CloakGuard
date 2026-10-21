"""Add hostname and registrable-domain columns. Does not invent historical timestamps."""

import csv
from pathlib import Path

import tldextract

REPO = Path(__file__).resolve().parents[1]
PATH = REPO / "data" / "manifests" / "capture_inventory.csv"
extract = tldextract.TLDExtract(suffix_list_urls=None)


def registrable(host: str) -> str:
    if not host or host.replace(".", "").isdigit():
        return ""
    parsed = extract(host)
    if not parsed.domain or not parsed.suffix:
        return host
    return f"{parsed.domain}.{parsed.suffix}"


def main() -> None:
    with PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0].keys())
    for name in ("hostname_group", "registrable_domain_group"):
        if name not in fields:
            fields.append(name)
    for row in rows:
        host = row.get("site_group") or row.get("hostname_group") or ""
        row["hostname_group"] = host
        row["registrable_domain_group"] = registrable(host)
    with PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    hosts = {row["hostname_group"] for row in rows}
    domains = {row["registrable_domain_group"] for row in rows}
    print(f"rows {len(rows)} hostnames {len(hosts)} registrable {len(domains)}")


if __name__ == "__main__":
    main()
