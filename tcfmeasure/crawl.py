"""C) Main measurement with OpenWPM (Linux server).

    python -m tcfmeasure.crawl datadir/tcfmeasure/<prefilter run>/tcf_sites.csv
    python -m tcfmeasure.crawl <tcf_sites.csv> --limit 10 --num-browsers 1    # pilot

Every site is visited once per variant (reject, accept, settings), each visit in a fresh profile
(reset=True). Variants run in rounds: first all sites "reject", then all "accept", then all
"settings", so visits of the same site are spread over time (fewer bot blocks).

Output: datadir/tcfmeasure/crawl-<timestamp>/ with crawl-data.sqlite (tcf_* tables plus OpenWPM's
http_requests, javascript_cookies, ...), screenshots/, openwpm.log and run_metadata.json.
"""
import argparse
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

from openwpm.command_sequence import CommandSequence
from openwpm.config import BrowserParams, ManagerParams
from openwpm.storage.sql_provider import BCSQLiteStorageProvider
from openwpm.task_manager import TaskManager

from tcfmeasure import config
from tcfmeasure.local_run import read_sites
from tcfmeasure.openwpm_command import TCFVisitCommand
from tcfmeasure.run_metadata import new_metadata, write_metadata


def firefox_version():
    """Version of OpenWPM's Firefox from firefox-bin/application.ini."""
    ini = config.REPO_DIR / "firefox-bin" / "application.ini"
    if not ini.exists():
        return None
    for line in ini.read_text().splitlines():
        if line.startswith("Version="):
            return line.split("=", 1)[1]
    return None


def make_browser_params(num_browsers, headless):
    params = [BrowserParams(display_mode="headless" if headless else "native") for _ in range(num_browsers)]
    for browser in params:
        browser.http_instrument = True        # gdpr_consent in GET/POST requests
        browser.cookie_instrument = True      # TCF cookies (euconsent-v2, ...)
        browser.js_instrument = False
        browser.navigation_instrument = False
        browser.callstack_instrument = False
        browser.dns_instrument = False
        browser.bot_mitigation = False
        browser.prefs["intl.accept_languages"] = config.ACCEPT_LANGUAGES
    return params


def as_text(params):
    return {key: str(value) for key, value in dataclasses.asdict(params).items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sites", help="tcf_sites.csv from the prefilter")
    parser.add_argument("--limit", type=int, help="only the first N sites (pilot)")
    parser.add_argument("--num-browsers", type=int, default=1)
    parser.add_argument("--variants", nargs="+", default=config.VARIANTS, choices=config.VARIANTS)
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    output_dir = config.OUTPUT_DIR / ("crawl-" + datetime.now().strftime("%Y-%m-%d--%H-%M-%S"))
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    sites = read_sites(args.sites, args.limit)

    browser_params = make_browser_params(args.num_browsers, headless=not args.headful)
    manager_params = ManagerParams(num_browsers=args.num_browsers)
    manager_params.data_directory = output_dir
    manager_params.log_path = output_dir / "openwpm.log"
    manager_params.memory_watchdog = True
    manager_params.process_watchdog = True

    metadata = new_metadata(
        "crawl", sites=args.sites, prefilter_metadata=str(Path(args.sites).parent / "run_metadata.json"),
        site_count=len(sites), variants=args.variants, arguments=vars(args),
        firefox_version=firefox_version(), accept_languages=config.ACCEPT_LANGUAGES,
        browser_params=as_text(browser_params[0]), manager_params=as_text(manager_params),
    )
    write_metadata(metadata, output_dir)

    manager = TaskManager(
        manager_params_temp=manager_params,
        browser_params_temp=browser_params,
        structured_storage_provider=BCSQLiteStorageProvider(db_path=output_dir / "crawl-data.sqlite"),
        unstructured_storage_provider=None,
    )
    try:
        for variant in args.variants:
            for site in sites:
                sequence = CommandSequence(site["url"], reset=True, site_rank=int(site["rank"]))
                sequence.append_command(TCFVisitCommand(site["url"], site["domain"], variant, screenshot_dir),
                                        timeout=config.COMMAND_TIMEOUT)
                manager.execute_command_sequence(sequence)
    finally:
        manager.close()
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_metadata(metadata, output_dir)
    print(f"-> {output_dir}")


if __name__ == "__main__":
    main()
