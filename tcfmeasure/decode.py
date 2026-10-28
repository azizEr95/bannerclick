"""D) Decodes every TC string of a measurement database into the table tc_decoded.

    python -m tcfmeasure.decode datadir/tcfmeasure/crawl-<...>/crawl-data.sqlite

Takes the TC strings reported by __tcfapi and the ones found in cookie/localStorage
(tcf_snapshots.tc_string and storage_tc_string); strings already decoded are skipped.
"""
import argparse
import sqlite3

from tcfmeasure.store import SCHEMA, sql_row
from tcfmeasure.tcstring import decode_many, library_version


def decode_database(path):
    """Decodes all TC strings of the database that are not decoded yet; returns a status line."""
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    strings = {row[0] for row in db.execute(
        "SELECT tc_string FROM tcf_snapshots WHERE tc_string IS NOT NULL "
        "UNION SELECT storage_tc_string FROM tcf_snapshots WHERE storage_tc_string IS NOT NULL")}
    done = {row[0] for row in db.execute("SELECT tc_string FROM tc_decoded")}
    todo = sorted(strings - done)

    decoder = f"@iabtechlabtcf/core {library_version()}"
    for decoded in decode_many(todo):
        row = sql_row({**decoded, "decoder": decoder})
        db.execute(f"INSERT OR REPLACE INTO tc_decoded ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                   list(row.values()))
    db.commit()
    errors = db.execute("SELECT COUNT(*) FROM tc_decoded WHERE error IS NOT NULL").fetchone()[0]
    return f"{len(todo)} new TC strings decoded ({len(done)} already there, {errors} with errors) with {decoder}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("database")
    print(decode_database(parser.parse_args().database))


if __name__ == "__main__":
    main()
