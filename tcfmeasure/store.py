"""Saves visit results into the tables of tcfmeasure/schema.sql, either through OpenWPM's storage
controller (crawler) or into a local SQLite file (local test run, semi-automatic mode)."""
import json
import sqlite3

from tcfmeasure.config import REPO_DIR

SCHEMA = (REPO_DIR / "tcfmeasure" / "schema.sql").read_text()


def to_sql_value(value):
    """Lists and dicts are stored as JSON text."""
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value


def sql_row(row):
    return {key: to_sql_value(value) for key, value in row.items()}


class LocalStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def next_visit_id(self):
        return (self.db.execute("SELECT MAX(visit_id) FROM tcf_visits").fetchone()[0] or 0) + 1

    def save(self, table, row):
        row = sql_row(row)
        columns = ", ".join(row)
        self.db.execute(f"INSERT INTO {table} ({columns}) VALUES ({', '.join('?' * len(row))})",
                        list(row.values()))
        self.db.commit()


class OpenWPMStore:
    def __init__(self, storage_controller_address):
        from openwpm.storage.storage_controller import DataSocket
        self.socket = DataSocket(storage_controller_address, client_name="tcfmeasure")

    def save(self, table, row):
        from openwpm.storage.storage_providers import TableName
        self.socket.store_record(TableName(table), row["visit_id"], sql_row(row))


def save_visit(store, result):
    """result: output of visit.run_variant (visit row, snapshots, events), visit_id already set."""
    store.save("tcf_visits", result["visit"])
    for snapshot in result["snapshots"]:
        store.save("tcf_snapshots", snapshot)
    for event in result["events"]:
        store.save("tcf_events", event)
