"""Accuracy of the crawler: compares crawler results with the manual check of the same sites.

    python -m tcfmeasure.compare <crawl-data.sqlite> <manual tcf.sqlite> [--out-dir DIR]

Both databases are decoded first (tcfmeasure.decode), so signals that only exist as cookie
TC string can be compared too. Per site and variant the last visit without error is used.

Output (default: next to the manual database):
  comparison.csv          one row per site, variant and field: crawler value, manual value, match
  comparison_summary.csv  per field: compared pairs, matches, accuracy in %
Fields: cookiewall, reject_level, deselected switches, preselected (V3), consent before (V1),
purpose consents / legitimate interests after the choice, >= 1 consent after reject (V4 lax),
accept_result.
"""
import argparse
import csv
import json
import sqlite3
from pathlib import Path

from tcfmeasure.decode import decode_database

AFTER_PHASES = [("after_action", "api"), ("reload", "api"), ("after_action", "cookie")]


class Results:
    """Read access to one measurement database (crawler or manual)."""

    def __init__(self, path):
        decode_database(path)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row

    def visit(self, domain, variant):
        return self.db.execute(
            "SELECT * FROM tcf_visits WHERE domain = ? AND variant = ? AND error IS NULL "
            "ORDER BY visit_id DESC LIMIT 1", (domain, variant)).fetchone()

    def domains(self):
        return [row[0] for row in self.db.execute("SELECT DISTINCT domain FROM tcf_visits ORDER BY domain")]

    def purposes(self, visit, phases):
        """(purpose consents, purpose LIs) of the first snapshot found for the given
        (phase, source) pairs; cookie TC strings are taken from tc_decoded."""
        if visit is None:
            return None, None
        for phase, source in phases:
            row = self.db.execute(
                "SELECT s.purpose_consents, s.purpose_li, d.purpose_consents AS d_consents, d.purpose_li AS d_li "
                "FROM tcf_snapshots s LEFT JOIN tc_decoded d ON d.tc_string = s.tc_string "
                "WHERE s.visit_id = ? AND s.phase = ? AND s.source = ?",
                (visit["visit_id"], phase, source)).fetchone()
            if row:
                consents = row["purpose_consents"] if source == "api" else row["d_consents"]
                li = row["purpose_li"] if source == "api" else row["d_li"]
                return as_list(consents), as_list(li)
        return None, None


def as_list(text):
    value = json.loads(text) if text else None
    return sorted(value) if isinstance(value, list) else None


def any_consent(consents):
    return None if consents is None else len(consents) > 0


def is_cookiewall(visit):
    return None if visit is None else bool(visit["cookiewall"]) or visit["reject_level"] == "cookiewall"


def preselected_crawler(crawler, domain):
    """V3 by the crawler: switches checked on level 2 in the settings variant (else reject variant)."""
    for variant in ("settings", "reject"):
        visit = crawler.visit(domain, variant)
        if visit is not None and visit["toggles_total"]:
            return "ja" if visit["toggles_preselected"] else "nein"
    return None


def compare_site(crawler, manual, domain):
    rows = []

    def add(variant, field, crawler_value, manual_value):
        both = crawler_value is not None and manual_value is not None
        rows.append({"domain": domain, "variant": variant, "field": field,
                     "crawler": json.dumps(crawler_value, ensure_ascii=False),
                     "manual": json.dumps(manual_value, ensure_ascii=False),
                     "match": (crawler_value == manual_value) if both else None})

    c_rej, m_rej = crawler.visit(domain, "reject"), manual.visit(domain, "reject")
    add("reject", "cookiewall", is_cookiewall(c_rej), is_cookiewall(m_rej))
    add("reject", "reject_level", c_rej and c_rej["reject_level"], m_rej and m_rej["reject_level"])
    if c_rej and m_rej and c_rej["reject_level"] == m_rej["reject_level"] == "2":
        add("reject", "deselected", c_rej["toggles_deselected"], m_rej["manual_deselected"])
    manual_pre = m_rej and m_rej["manual_preselected"]
    add("reject", "preselected (V3)", preselected_crawler(crawler, domain),
        manual_pre if manual_pre in ("ja", "nein") else None)

    c_before, _ = crawler.purposes(c_rej, [("before", "api"), ("before", "cookie")])
    m_before, _ = manual.purposes(m_rej, [("before", "api"), ("before", "cookie")])
    add("reject", "consent before (V1)", any_consent(c_before), any_consent(m_before))

    c_after, c_li = crawler.purposes(c_rej, AFTER_PHASES)
    m_after, m_li = manual.purposes(m_rej, AFTER_PHASES)
    add("reject", "purpose consents after", c_after, m_after)
    add("reject", "purpose LI after", c_li, m_li)
    add("reject", ">= 1 consent after reject (V4 lax)", any_consent(c_after), any_consent(m_after))

    c_acc, m_acc = crawler.visit(domain, "accept"), manual.visit(domain, "accept")
    add("accept", "accept_result", c_acc and c_acc["accept_result"], m_acc and m_acc["accept_result"])
    c_after, _ = crawler.purposes(c_acc, AFTER_PHASES)
    m_after, _ = manual.purposes(m_acc, AFTER_PHASES)
    add("accept", "purpose consents after", c_after, m_after)
    return rows


def summarize(rows):
    summary = {}
    for row in rows:
        key = (row["variant"], row["field"])
        entry = summary.setdefault(key, {"variant": key[0], "field": key[1], "compared": 0, "matches": 0})
        if row["match"] is not None:
            entry["compared"] += 1
            entry["matches"] += int(row["match"])
    for entry in summary.values():
        entry["accuracy_percent"] = round(100 * entry["matches"] / entry["compared"], 1) if entry["compared"] else None
    return list(summary.values())


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("crawler_db")
    parser.add_argument("manual_db")
    parser.add_argument("--out-dir", help="default: directory of the manual database")
    args = parser.parse_args()

    crawler, manual = Results(args.crawler_db), Results(args.manual_db)
    rows = [row for domain in manual.domains() for row in compare_site(crawler, manual, domain)]
    summary = summarize(rows)

    out_dir = Path(args.out_dir or Path(args.manual_db).parent)
    write_csv(out_dir / "comparison.csv", rows)
    write_csv(out_dir / "comparison_summary.csv", summary)
    for entry in summary:
        print(f"{entry['variant']:<7} {entry['field']:<38} {entry['matches']:>3}/{entry['compared']:<3} "
              f"{entry['accuracy_percent'] if entry['accuracy_percent'] is not None else '-':>6} %")
    print(f"-> {out_dir / 'comparison.csv'}")


if __name__ == "__main__":
    main()
