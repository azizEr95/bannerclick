"""A) Select the first N domains with a given TLD (default: 1000 x .de) from a Tranco list.

Without arguments the latest daily Tranco list is used and its list ID is stored next to the result:

    python -m tcfmeasure.tranco_de                      # latest list, first 1000 .de domains
    python -m tcfmeasure.tranco_de --list-id GQ3LK      # a fixed list
    python -m tcfmeasure.tranco_de --csv top-1m.csv --list-id GQ3LK   # an already downloaded list

Output: tcfmeasure/lists/tranco_<ID>_de_top<N>.csv (rank,domain) and a .json with the list metadata.
"""
import argparse
import csv
import io
import json
import urllib.request
from datetime import datetime, timezone

from tcfmeasure import config

LATEST_ID_URL = "https://tranco-list.eu/top-1m-id"
LIST_INFO_URL = "https://tranco-list.eu/api/lists/id/{list_id}"
DOWNLOAD_URL = "https://tranco-list.eu/download/{list_id}/1000000"


def fetch_text(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode().strip()


def latest_list_id():
    return fetch_text(LATEST_ID_URL)


def list_info(list_id):
    """Metadata of the list (creation date, configuration) as returned by the Tranco API, or None."""
    try:
        return json.loads(fetch_text(LIST_INFO_URL.format(list_id=list_id)))
    except Exception:
        return None


def ranked_domains(lines):
    """Yields (rank, domain) for every row of a Tranco CSV ("rank,domain")."""
    for row in csv.reader(lines):
        if len(row) >= 2 and row[0].isdigit():
            yield int(row[0]), row[1].strip().lower()


def first_with_tld(rows, tld, n):
    """The first n (rank, domain) pairs whose domain ends with tld. Stops reading as soon as n are found."""
    selected = []
    for rank, domain in rows:
        if domain.endswith(tld):
            selected.append((rank, domain))
            if len(selected) == n:
                break
    return selected


def select_from_download(list_id, tld, n):
    """Streams the list from tranco-list.eu, so only the part up to the n-th match is downloaded."""
    with urllib.request.urlopen(DOWNLOAD_URL.format(list_id=list_id), timeout=120) as response:
        return first_with_tld(ranked_domains(io.TextIOWrapper(response, encoding="utf-8")), tld, n)


def select_from_file(path, tld, n):
    with open(path, newline="", encoding="utf-8") as f:
        return first_with_tld(ranked_domains(f), tld, n)


def write_result(selected, list_id, tld, n, source):
    config.LISTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"tranco_{list_id}_{tld.strip('.')}_top{n}"
    csv_path = config.LISTS_DIR / f"{stem}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "domain"])
        writer.writerows(selected)

    metadata = {
        "tranco_list_id": list_id,
        "tranco_list_info": list_info(list_id),
        "source": source,
        "tld": tld,
        "requested_n": n,
        "selected_n": len(selected),
        "last_rank": selected[-1][0] if selected else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (config.LISTS_DIR / f"{stem}.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    return csv_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=config.TRANCO_TOP_N, help="number of domains to select")
    parser.add_argument("--tld", default=config.TRANCO_TLD, help="domain ending to filter for")
    parser.add_argument("--list-id", help="Tranco list ID (default: latest daily list)")
    parser.add_argument("--csv", help="use this local Tranco CSV instead of downloading (needs --list-id)")
    args = parser.parse_args()

    if args.csv and not args.list_id:
        parser.error("--csv needs --list-id, otherwise the list cannot be identified later")

    list_id = args.list_id or latest_list_id()
    if args.csv:
        selected = select_from_file(args.csv, args.tld, args.n)
        source = args.csv
    else:
        selected = select_from_download(list_id, args.tld, args.n)
        source = DOWNLOAD_URL.format(list_id=list_id)

    path = write_result(selected, list_id, args.tld, args.n, source)
    last_rank = selected[-1][0] if selected else None
    print(f"Tranco list {list_id}: {len(selected)} {args.tld} domains (up to rank {last_rank}) -> {path}")
    if len(selected) < args.n:
        print(f"Warning: only {len(selected)} of {args.n} requested domains found")


if __name__ == "__main__":
    main()
