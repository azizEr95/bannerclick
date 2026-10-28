"""Runs the measurement variants with plain Selenium instead of OpenWPM (no request logging),
e.g. to test changes on the Mac before a crawl. Same visit logic and tables as the crawler.

    python -m tcfmeasure.local_run datadir/tcfmeasure/<prefilter run>/tcf_sites.csv --limit 5
    python -m tcfmeasure.local_run <sites.csv> --variants reject

Variants run in rounds (all sites reject, then all accept, ...), so visits of the same site
are spread over time (fewer bot blocks).
"""
import argparse
import csv
import time
from datetime import datetime

from tcfmeasure import config
from tcfmeasure.browser import browser_versions, start_firefox
from tcfmeasure.run_metadata import new_metadata, write_metadata
from tcfmeasure.store import LocalStore, save_visit
from tcfmeasure.visit import run_variant, set_visit_id


def read_sites(path, limit=None):
    """Sites of tcf_sites.csv (or a sample), without duplicates, with the URL to measure."""
    with open(path, newline="", encoding="utf-8") as f:
        sites = [row for row in csv.DictReader(f) if not row.get("duplicate_of")]
    for site in sites:
        site["url"] = site.get("browser_final_url") or f"https://{site['domain']}/"
    return sites[:limit] if limit else sites


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sites", help="tcf_sites.csv from the prefilter or a sample")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--variants", nargs="+", default=config.VARIANTS, choices=config.VARIANTS)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--firefox-binary")
    parser.add_argument("--geckodriver")
    args = parser.parse_args()

    output_dir = config.OUTPUT_DIR / ("local-" + datetime.now().strftime("%Y-%m-%d--%H-%M-%S"))
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    store = LocalStore(output_dir / "tcf.sqlite")
    sites = read_sites(args.sites, args.limit)
    metadata = new_metadata("local_run", sites=args.sites, variants=args.variants, arguments=vars(args))
    write_metadata(metadata, output_dir)

    for variant in args.variants:
        for i, site in enumerate(sites, start=1):
            driver = start_firefox(args.firefox_binary, args.geckodriver, headless=not args.headful)
            metadata.setdefault("browser", browser_versions(driver))
            try:
                result = run_variant(driver, site["url"], site["domain"], variant,
                                     screenshot_dir / f"{site['domain']}_{variant}", mode="local")
            except Exception as e:
                result = {"visit": {"mode": "local", "domain": site["domain"], "url": site["url"],
                                    "variant": variant, "error": repr(e)}, "snapshots": [], "events": []}
            finally:
                driver.quit()
            set_visit_id(result, store.next_visit_id())
            save_visit(store, result)
            visit = result["visit"]
            print(f"[{variant} {i}/{len(sites)}] {site['domain']}: reject_level={visit.get('reject_level')} "
                  f"accept={visit.get('accept_result')} cookiewall={visit.get('cookiewall')} "
                  f"signal={visit.get('signal_source')} bot_blocked={visit.get('bot_blocked')} "
                  f"error={visit.get('error')}")
            time.sleep(config.PAUSE_BETWEEN_DOMAINS)

    write_metadata(metadata, output_dir)
    print(f"-> {output_dir}")


if __name__ == "__main__":
    main()
