"""B) Prefilter crawl: which domains are reachable, allowed by robots.txt and run a TCF v2 CMP?

For every domain (in this order, a domain drops out at the first failing step):
  1. HTTP GET of the start page: status code and redirect target. The domain goes on if the
     status is < 400 or a typical bot block (403, 429, 503), since the browser may still get through.
  2. robots.txt of the final host allows the start page for user agent "*" (decided with Protego,
     RFC 9309). What Python's urllib.robotparser (used by Matte et al.) would decide is stored too.
  3. Firefox with a fresh profile loads the page (reachable = loaded in the browser);
     __tcfapi('ping') is polled for up to TCF_WAIT seconds, until the CMP reports cmpLoaded.
     The API is found as __tcfapi function or, if only the __tcfapiLocator frame exists, via postMessage.
Redirects are not excluded but marked: final domain, other domain, other TLD, and duplicates
(several input domains ending on the same final domain). The final page is what gets measured.

    python -m tcfmeasure.prefilter tcfmeasure/lists/tranco_<ID>_de_top1000.csv
    python -m tcfmeasure.prefilter <list.csv> --limit 10                  # test run
    python -m tcfmeasure.prefilter <list.csv> --output-dir <dir of a run>  # resume / recompute funnel

Output directory: prefilter.sqlite (one row per domain), prefilter.csv, funnel.csv, notes.csv,
tcf_sites.csv (input for the main measurement) and run_metadata.json.
"""
import argparse
import csv
import json
import sqlite3
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import tldextract
from protego import Protego
from selenium.common.exceptions import TimeoutException, WebDriverException

from tcfmeasure import config
from tcfmeasure.browser import browser_versions, start_firefox
from tcfmeasure.run_metadata import new_metadata, write_metadata

PING_JS = (Path(__file__).parent / "js" / "tcf_ping.js").read_text()

# Status codes that usually mean "bot blocked" rather than "site down": the browser is tried anyway.
BOT_BLOCK_STATUSES = {403, 429, 503}

# Public Suffix List snapshot bundled with tldextract; no download, so results are reproducible.
DOMAIN_PARTS = tldextract.TLDExtract(suffix_list_urls=())

COLUMNS = [
    "rank", "domain", "checked_at",
    # 1. HTTP
    "http_url", "http_status", "http_final_url", "http_error",
    # 2. robots.txt
    "robots_url", "robots_status", "robots_allowed", "robots_allowed_urllib",
    # 3. Browser and TCF
    "reachable", "browser_error", "browser_final_url", "page_title",
    "has_tcfapi", "has_locator", "ping_via", "seconds_to_tcf", "seconds_to_cmp_loaded",
    "cmp_loaded", "cmp_status", "display_status", "cmp_id", "cmp_version",
    "gdpr_applies", "tcf_policy_version", "api_version", "gvl_version", "ping_json",
    # Redirects
    "final_host", "final_domain", "redirect_other_domain", "redirect_other_tld", "duplicate_of",
]


# ---------- 1. HTTP ----------

def http_get(url):
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    return urllib.request.urlopen(request, timeout=config.HTTP_TIMEOUT)


def check_http(domain):
    """Tries https://domain, https://www.domain and http://domain; the first one that answers counts."""
    error = None
    for url in (f"https://{domain}/", f"https://www.{domain}/", f"http://{domain}/"):
        try:
            with http_get(url) as response:
                return {"http_url": url, "http_status": response.status, "http_final_url": response.geturl()}
        except urllib.error.HTTPError as e:  # the server answered, but with an error status
            return {"http_url": url, "http_status": e.code, "http_final_url": e.geturl() or url}
        except Exception as e:
            error = repr(e)
    return {"http_error": error}


def worth_a_browser_try(row):
    status = row.get("http_status")
    return status is not None and (status < 400 or status in BOT_BLOCK_STATUSES)


# ---------- 2. robots.txt ----------

def fetch_robots(robots_url):
    """Returns (status, content); status is None if robots.txt could not be fetched at all."""
    try:
        with http_get(robots_url) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


def protego_decision(status, content, page_url):
    """RFC 9309: a 4xx robots.txt allows everything, a 5xx or unreachable one disallows everything."""
    if status is None or status >= 500:
        return False
    if status >= 400:
        return True
    return Protego.parse(content).can_fetch(page_url, config.ROBOTS_USER_AGENT)


def urllib_decision(status, content, page_url):
    """What Python's urllib.robotparser would decide for the same response, following
    RobotFileParser.read(): 401/403 disallow everything, other 4xx allow everything, 5xx or
    no response disallow. Its parser has no wildcards, uses the first instead of the longest
    match, and turns "Disallow: /?" into "Disallow: /"."""
    if status is None or status >= 500 or status in (401, 403):
        return False
    if status >= 400:
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(content.splitlines())
    return parser.can_fetch(config.ROBOTS_USER_AGENT, page_url)


def check_robots(page_url):
    robots_url = urljoin(page_url, "/robots.txt")
    status, content = fetch_robots(robots_url)
    return {
        "robots_url": robots_url,
        "robots_status": status,
        "robots_allowed": protego_decision(status, content, page_url),
        "robots_allowed_urllib": urllib_decision(status, content, page_url),
    }


# ---------- 3. Browser and TCF ----------

def tcf_ping(driver):
    try:
        return driver.execute_async_script(PING_JS, config.TCF_CALL_TIMEOUT * 1000)
    except WebDriverException:
        return None


def load_page(driver, url):
    """Returns (loaded, error). A page load timeout still counts as loaded: the page is there,
    only some resource is still pending, and the CMP may already run."""
    try:
        driver.get(url)
        return True, None
    except TimeoutException:
        return True, "page load timeout"
    except WebDriverException as e:
        return False, e.msg


def check_tcf(driver, url):
    result = {}
    result["reachable"], result["browser_error"] = load_page(driver, url)
    if not result["reachable"]:
        return result
    loaded_at = time.monotonic()

    last = None
    while True:
        seconds = round(time.monotonic() - loaded_at, 1)
        ping = tcf_ping(driver)
        if ping:
            last = ping
            if (ping["has_tcfapi"] or ping["has_locator"]) and "seconds_to_tcf" not in result:
                result["seconds_to_tcf"] = seconds
            if ping["ping"] and ping["ping"].get("cmpLoaded"):
                result["seconds_to_cmp_loaded"] = seconds
                break
        if seconds >= config.TCF_WAIT:
            break
        time.sleep(config.TCF_POLL_INTERVAL)

    try:
        result["browser_final_url"] = driver.current_url
        result["page_title"] = driver.title  # helps to spot bot-block pages ("Access denied")
    except WebDriverException:
        pass
    if last:
        result.update(ping_fields(last))
    return result


def ping_fields(ping_result):
    ping = ping_result["ping"] or {}
    return {
        "has_tcfapi": ping_result["has_tcfapi"],
        "has_locator": ping_result["has_locator"],
        "ping_via": ping_result["ping_via"],
        "cmp_loaded": ping.get("cmpLoaded"),
        "cmp_status": ping.get("cmpStatus"),
        "display_status": ping.get("displayStatus"),
        "cmp_id": ping.get("cmpId"),
        "cmp_version": ping.get("cmpVersion"),
        "gdpr_applies": ping.get("gdprApplies"),
        "tcf_policy_version": ping.get("tcfPolicyVersion"),
        "api_version": ping.get("apiVersion"),
        "gvl_version": ping.get("gvlVersion"),
        "ping_json": json.dumps(ping_result["ping"]) if ping_result["ping"] else None,
    }


# ---------- Redirects ----------

def redirect_fields(domain, final_url):
    """Compares the registrable domain (eTLD+1) of the final page with the input domain."""
    host = urlsplit(final_url).hostname if final_url else None
    if not host:  # e.g. about:blank or a browser error page
        return {}
    final_parts = DOMAIN_PARTS(host)
    final_domain = final_parts.top_domain_under_public_suffix or host
    return {
        "final_host": host,
        "final_domain": final_domain,
        "redirect_other_domain": final_domain != domain,
        "redirect_other_tld": final_parts.suffix != DOMAIN_PARTS(domain).suffix,
    }


def mark_duplicates(rows):
    """Several input domains may end on the same final domain. The best-ranked one is kept as
    original, the others get duplicate_of = that domain."""
    first_by_final_domain = {}
    for row in sorted(rows, key=lambda row: row["rank"]):
        final_domain = row["final_domain"]
        if final_domain and final_domain in first_by_final_domain:
            row["duplicate_of"] = first_by_final_domain[final_domain]
        else:
            row["duplicate_of"] = None
            if final_domain:
                first_by_final_domain[final_domain] = row["domain"]


# ---------- One domain ----------

def check_domain(rank, domain, args, metadata):
    row = {"rank": rank, "domain": domain, "checked_at": datetime.now(timezone.utc).isoformat()}

    row.update(check_http(domain))
    if not worth_a_browser_try(row):
        row["reachable"] = False
        return row

    row.update(check_robots(row["http_final_url"]))
    if not row["robots_allowed"]:
        return row

    driver = None
    try:
        driver = start_firefox(args.firefox_binary, args.geckodriver, headless=not args.headful)
        if "browser" not in metadata:
            metadata["browser"] = browser_versions(driver)
        row.update(check_tcf(driver, row["http_url"]))
    except WebDriverException as e:
        row["browser_error"] = e.msg
    finally:
        if driver:
            driver.quit()

    row.update(redirect_fields(domain, row.get("browser_final_url")))
    return row


# ---------- Storage ----------

def open_db(path):
    db = sqlite3.connect(path)
    db.execute(f"CREATE TABLE IF NOT EXISTS prefilter ({', '.join(COLUMNS)}, PRIMARY KEY (domain))")
    return db


def save_row(db, row):
    values = [row.get(column) for column in COLUMNS]
    db.execute(f"INSERT OR REPLACE INTO prefilter VALUES ({', '.join('?' * len(COLUMNS))})", values)
    db.commit()


def all_rows(db):
    db.row_factory = sqlite3.Row
    return [dict(row) for row in db.execute("SELECT * FROM prefilter ORDER BY rank")]


def write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------- Funnel and notes ----------

def is_tcf_site(row):
    """Input for the main measurement: the CMP is loaded and GDPR applies."""
    return bool(row["cmp_loaded"]) and bool(row["gdpr_applies"])


FUNNEL_STEPS = [
    ("input", lambda row: True),
    ("HTTP < 400 or bot block (403/429/503)", worth_a_browser_try),
    ("robots.txt allows (Protego)", lambda row: row["robots_allowed"]),
    ("reachable (loaded in browser)", lambda row: row["reachable"]),
    ("TCF API present (__tcfapi or locator)", lambda row: row["has_tcfapi"] or row["has_locator"]),
    ("ping answered", lambda row: row["ping_via"] is not None),
    ("cmpLoaded", lambda row: row["cmp_loaded"]),
    ("gdprApplies", lambda row: row["gdpr_applies"]),
]


def funnel(rows):
    """Each step counts the domains that passed it and all previous steps."""
    table = []
    remaining = rows
    for step, passes in FUNNEL_STEPS:
        remaining = [row for row in remaining if passes(row)]
        share = 100 * len(remaining) / len(rows) if rows else 0
        table.append({"step": step, "domains": len(remaining), "percent_of_input": round(share, 1)})
    return table


def notes(rows):
    """Counts next to the funnel. SQLite stores booleans as 0/1, unchecked values as NULL (None)."""
    def count(condition):
        return sum(1 for row in rows if condition(row))

    robots_checked = [row for row in rows if row["robots_allowed"] is not None]
    return [
        {"note": "robots.txt disallows (excluded)", "domains": count(lambda r: r["robots_allowed"] == 0)},
        {"note": "urllib.robotparser would decide differently",
         "domains": sum(1 for r in robots_checked if r["robots_allowed"] != r["robots_allowed_urllib"])},
        {"note": "... of which urllib would exclude",
         "domains": sum(1 for r in robots_checked if r["robots_allowed"] == 1 and r["robots_allowed_urllib"] == 0)},
        {"note": "... of which urllib would include",
         "domains": sum(1 for r in robots_checked if r["robots_allowed"] == 0 and r["robots_allowed_urllib"] == 1)},
        {"note": "HTTP bot block (403/429/503), but loaded in browser",
         "domains": count(lambda r: r["http_status"] in BOT_BLOCK_STATUSES and r["reachable"] == 1)},
        {"note": "redirect to other domain", "domains": count(lambda r: r["redirect_other_domain"] == 1)},
        {"note": "redirect to other TLD", "domains": count(lambda r: r["redirect_other_tld"] == 1)},
        {"note": "duplicate final domain", "domains": count(lambda r: r["duplicate_of"] is not None)},
        {"note": "TCF sites that are duplicates", "domains": count(lambda r: is_tcf_site(r) and r["duplicate_of"])},
    ]


# ---------- Main ----------

def read_domain_list(path, limit):
    with open(path, newline="", encoding="utf-8") as f:
        rows = [(int(row["rank"]), row["domain"]) for row in csv.DictReader(f)]
    return rows[:limit] if limit else rows


def tranco_list_metadata(list_path):
    """The .json written by tranco_de.py next to the list, if there is one."""
    path = Path(list_path).with_suffix(".json")
    return json.loads(path.read_text()) if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("domain_list", help="CSV with columns rank,domain (output of tranco_de.py)")
    parser.add_argument("--limit", type=int, help="only check the first N domains of the list")
    parser.add_argument("--output-dir", help="existing run directory: skip domains already checked")
    parser.add_argument("--headful", action="store_true", help="show the browser window")
    parser.add_argument("--firefox-binary", help="Firefox binary (default: $TCF_FIREFOX or firefox-bin/firefox)")
    parser.add_argument("--geckodriver", help="geckodriver binary (default: $TCF_GECKODRIVER or found by Selenium)")
    args = parser.parse_args()

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = config.OUTPUT_DIR / ("prefilter-" + datetime.now().strftime("%Y-%m-%d--%H-%M-%S"))
    output_dir.mkdir(parents=True, exist_ok=True)

    domains = read_domain_list(args.domain_list, args.limit)
    db = open_db(output_dir / "prefilter.sqlite")
    done = {row[0] for row in db.execute("SELECT domain FROM prefilter")}

    metadata = new_metadata(
        "prefilter",
        domain_list=str(args.domain_list),
        tranco=tranco_list_metadata(args.domain_list),
        limit=args.limit,
        arguments=vars(args),
    )
    previous = output_dir / "run_metadata.json"
    if previous.exists():  # resumed run: keep the metadata of the earlier part(s)
        old = json.loads(previous.read_text())
        metadata["previous_runs"] = old.pop("previous_runs", []) + [old]
    write_metadata(metadata, output_dir)

    todo = [(rank, domain) for rank, domain in domains if domain not in done]
    print(f"{len(domains)} domains, {len(done)} already checked, {len(todo)} to do -> {output_dir}")
    for i, (rank, domain) in enumerate(todo, start=1):
        try:
            row = check_domain(rank, domain, args, metadata)
        except Exception as e:  # never stop the whole crawl because of one domain
            row = {"rank": rank, "domain": domain, "checked_at": datetime.now(timezone.utc).isoformat(),
                   "browser_error": f"unexpected: {e!r}"}
        save_row(db, row)
        print(f"[{i}/{len(todo)}] {domain}: HTTP {row.get('http_status')}, robots {row.get('robots_allowed')} "
              f"(urllib {row.get('robots_allowed_urllib')}), loaded {row.get('reachable')}, "
              f"final {row.get('final_domain')}, cmpLoaded {row.get('cmp_loaded')}, cmpId {row.get('cmp_id')}")
        time.sleep(config.PAUSE_BETWEEN_DOMAINS)

    rows = all_rows(db)
    mark_duplicates(rows)
    for row in rows:
        save_row(db, row)
    funnel_table = funnel(rows)
    notes_table = notes(rows)
    write_csv(output_dir / "prefilter.csv", rows, COLUMNS)
    write_csv(output_dir / "funnel.csv", funnel_table, ["step", "domains", "percent_of_input"])
    write_csv(output_dir / "notes.csv", notes_table, ["note", "domains"])
    write_csv(output_dir / "tcf_sites.csv", [row for row in rows if is_tcf_site(row)],
              ["rank", "domain", "browser_final_url", "final_domain",
               "redirect_other_domain", "redirect_other_tld", "duplicate_of"])

    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    metadata["funnel"] = funnel_table
    metadata["notes"] = notes_table
    write_metadata(metadata, output_dir)

    print()
    for step in funnel_table:
        print(f"{step['step']:<45} {step['domains']:>5}  {step['percent_of_input']:>5} %")
    print()
    for note in notes_table:
        print(f"{note['note']:<52} {note['domains']:>5}")


if __name__ == "__main__":
    main()
