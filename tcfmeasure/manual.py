"""C5) Semi-automatic mode: a visible Firefox (plain Selenium, no OpenWPM) on your own computer.
A person clicks, the script records the TCF signal exactly like the crawler (visit.py).

    python -m tcfmeasure.manual datadir/tcfmeasure/<prefilter run>/sample_30_seed<...>.csv
    python -m tcfmeasure.manual <sample.csv> --output-dir datadir/tcfmeasure/manual-<...>   # resume

Per site and variant (reject, then accept; each in a fresh profile, in rounds like the crawler):
the page is loaded, the script waits 60 s (as the crawler does), then asks you to click in the
browser and to answer a few questions in the terminal. Afterwards it reads the signal, reloads
after 3 s and reads it again. Requests with gdpr_consent are only recorded for GET requests of
the top frame (Resource Timing API).
"""
import argparse
import time
from datetime import datetime

from tcfmeasure import config
from tcfmeasure.browser import browser_versions, start_firefox
from tcfmeasure.local_run import read_sites
from tcfmeasure.reject import ACTION_WAIT, wait_until
from tcfmeasure.run_metadata import new_metadata, write_metadata
from tcfmeasure.store import LocalStore, save_visit
from tcfmeasure.visit import run_variant, set_visit_id

VARIANTS = ["reject", "accept"]

REJECT_INSTRUCTIONS = """
  ABLEHNEN nach Matte et al., Anhang D:
  - Ebene 1: "Ablehnen" / "Alle ablehnen" / "Nur notwendige" klicken, falls vorhanden.
  - Sonst Einstellungen öffnen (Ebene 2): zuerst "Alle ablehnen"/"Alle abwählen".
    Sonst ALLE nicht deaktivierten Zweck-Schalter abwählen (Vendoren ignorieren), dann speichern.
  - Nie einen Button mit "akzeptieren/zustimmen" zum Schließen verwenden
    (Ausnahme: "Nur notwendige akzeptieren").
  - Cookiewall (Zustimmen oder bezahlen): NICHTS klicken.
"""
ACCEPT_INSTRUCTIONS = """
  AKZEPTIEREN: "Alle akzeptieren" (bzw. "Zustimmen") auf Ebene 1 klicken.
"""


def ask(question, choices=None):
    while True:
        answer = input(f"  {question} ").strip()
        if not choices or answer in choices:
            return answer
        print(f"  Bitte eine der Antworten eingeben: {', '.join(choices)}")


def manual_reject(driver, watcher):
    print(REJECT_INSTRUCTIONS)
    input("  Jetzt im Browser ablehnen. Danach hier Enter drücken ... ")
    level = ask("Ebene des Ablehnens? [1/2/none/cookiewall/unklar]:", ["1", "2", "none", "cookiewall", "unklar"])
    deselected = ask("Wie viele Schalter hast du abgewählt? [Zahl, 0 wenn keine]:")
    preselected = ask("Waren auf Ebene 2 Zwecke vorausgewählt? [ja/nein/nicht angesehen]:",
                      ["ja", "nein", "nicht angesehen"])
    note = ask("Notiz (optional):")
    done = level != "cookiewall" and wait_until(watcher.is_done, ACTION_WAIT)
    return {"reject_level": level, "useractioncomplete": done,
            "manual_level": level, "manual_deselected": int(deselected) if deselected.isdigit() else None,
            "manual_preselected": preselected, "manual_note": note or None,
            "cookiewall_reason": "manual" if level == "cookiewall" else None}


def manual_accept(driver, watcher):
    print(ACCEPT_INSTRUCTIONS)
    input("  Jetzt im Browser akzeptieren. Danach hier Enter drücken ... ")
    result = ask("Ergebnis? [accepted/unklar]:", ["accepted", "unklar"])
    cookiewall = ask("War es eine Cookiewall? [ja/nein]:", ["ja", "nein"])
    note = ask("Notiz (optional):")
    done = wait_until(watcher.is_done, ACTION_WAIT)
    return {"accept_result": result, "useractioncomplete": done, "manual_level": result,
            "manual_note": note or None, "cookiewall_reason": "manual" if cookiewall == "ja" else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sites", help="sample CSV (tcfmeasure.sample) or tcf_sites.csv")
    parser.add_argument("--output-dir", help="existing manual run: continue where it stopped")
    parser.add_argument("--firefox-binary")
    parser.add_argument("--geckodriver")
    args = parser.parse_args()

    if args.output_dir:
        output_dir = config.REPO_DIR / args.output_dir
    else:
        output_dir = config.OUTPUT_DIR / ("manual-" + datetime.now().strftime("%Y-%m-%d--%H-%M-%S"))
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    store = LocalStore(output_dir / "tcf.sqlite")
    done = set(store.db.execute("SELECT domain, variant FROM tcf_visits WHERE error IS NULL").fetchall())
    sites = read_sites(args.sites)
    metadata = new_metadata("manual", sites=args.sites, variants=VARIANTS, arguments=vars(args))
    write_metadata(metadata, output_dir)

    actions = {"reject": manual_reject, "accept": manual_accept}
    for variant in VARIANTS:
        for i, site in enumerate(sites, start=1):
            if (site["domain"], variant) in done:
                continue
            print(f"\n=== [{variant} {i}/{len(sites)}] {site['domain']}  ({site['url']})")
            print(f"  Seite lädt, das Skript wartet {config.VISIT_WAIT} s wie der Crawler. Noch NICHT klicken.")
            driver = start_firefox(args.firefox_binary, args.geckodriver, headless=False)
            metadata.setdefault("browser", browser_versions(driver))
            try:
                result = run_variant(driver, site["url"], site["domain"], variant,
                                     screenshot_dir / f"{site['domain']}_{variant}", mode="manual",
                                     action=actions[variant])
            except Exception as e:
                result = {"visit": {"mode": "manual", "domain": site["domain"], "url": site["url"],
                                    "variant": variant, "error": repr(e)}, "snapshots": [], "events": []}
            finally:
                driver.quit()
            set_visit_id(result, store.next_visit_id())
            save_visit(store, result)
            visit = result["visit"]
            print(f"  gespeichert: signal={visit.get('signal_source')} useractioncomplete="
                  f"{visit.get('useractioncomplete')} bot_blocked={visit.get('bot_blocked')} error={visit.get('error')}")
            time.sleep(config.PAUSE_BETWEEN_DOMAINS)

    write_metadata(metadata, output_dir)
    print(f"-> {output_dir}")


if __name__ == "__main__":
    main()
