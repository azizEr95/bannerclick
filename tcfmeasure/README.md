# tcfmeasure – TCF v2.2 measurement for .de websites

Re-measurement of Matte, Bielova & Santos (2020), "Do Cookie Banners Respect my Choice?", for German
websites. This module sits next to BannerClick and does not change its core. Settings are in
[`config.py`](config.py), and every run writes them into `run_metadata.json`.

## Setup

**Linux server (automatic crawl):** run the regular BannerClick installation (`./install.sh`,
`conda activate openwpm`), then `pip install -r tcfmeasure/requirements.txt`. The scripts then use
`firefox-bin/firefox` (Firefox 121) and the geckodriver from the conda environment.

**Mac (tests, semi-automatic mode):** the scripts need only Python 3, `selenium==4.16.0`,
Firefox 121 and geckodriver 0.33.0:

```bash
python3 -m venv venv && venv/bin/pip install -r tcfmeasure/requirements.txt
# Firefox 121: https://archive.mozilla.org/pub/firefox/releases/121.0/mac/en-US/
# geckodriver 0.33.0: https://github.com/mozilla/geckodriver/releases/tag/v0.33.0
export TCF_FIREFOX="/path/to/Firefox.app/Contents/MacOS/firefox"
export TCF_GECKODRIVER="/path/to/geckodriver"
```

## A) Select the websites

```bash
python -m tcfmeasure.tranco_de                   # latest daily Tranco list, first 1000 .de domains
python -m tcfmeasure.tranco_de --list-id GQ3LK   # a fixed list ID, e.g. to reproduce a run
```

The result goes to `tcfmeasure/lists/tranco_<ID>_de_top<N>.csv` (`rank,domain`). The `.json` next to it
holds the list ID, the list's creation date and its Tranco configuration.

## B) Prefilter crawl

```bash
python -m tcfmeasure.prefilter tcfmeasure/lists/tranco_<ID>_de_top1000.csv --limit 10   # test
python -m tcfmeasure.prefilter tcfmeasure/lists/tranco_<ID>_de_top1000.csv              # full run
python -m tcfmeasure.prefilter <list.csv> --output-dir datadir/tcfmeasure/prefilter-<...>  # resume
```

The prefilter checks each domain in order and stops at the first step that fails:

1. **HTTP:** GET of `https://domain/`, then `https://www.domain/`, then `http://domain/`. The status
   and the redirect target are stored in their own columns. The domain moves on to the next step if
   the status is below 400, or if it is 403, 429 or 503. Those three usually mean the script was
   blocked as a bot, so the browser gets a try anyway.
2. **robots.txt:** checked on the final host for the user agent `*`.
   - The decision comes from [Protego](https://github.com/scrapy/protego), following RFC 9309. A 4xx
     robots.txt means everything is allowed. A 5xx robots.txt, or one that cannot be reached, means
     nothing is.
   - Disallowed domains are excluded but still counted.
   - `robots_allowed_urllib` stores what Python's `urllib.robotparser` would have decided for the same
     response. Matte et al. used it. It disallows everything on 401/403, has no wildcards, uses the
     first match instead of the longest, and turns `Disallow: /?` into `Disallow: /`.
3. **Browser:** Firefox loads the page with a fresh profile. *Reachable* means loaded in the browser.
   It then sends `__tcfapi('ping')` every 2 s, for at most 60 s, until `cmpLoaded` is true. When only
   the `__tcfapiLocator` frame exists, the ping goes through `postMessage`. The fields stored are
   `cmpLoaded`, `cmpStatus`, `displayStatus`, `cmpId`, `cmpVersion`, `gdprApplies`, `tcfPolicyVersion`
   and `gvlVersion`, plus the page title, which helps to spot bot-block pages.
4. **Redirects:** marked, not excluded. The final page is what gets measured. Stored are:
   - `final_domain`: the eTLD+1 of the page the browser ended on, taken from the Public Suffix List
     snapshot bundled with tldextract, with no download
   - `redirect_other_domain` and `redirect_other_tld`
   - `duplicate_of`: when several input domains end on the same final domain, the best-ranked one is
     the original and the others point to it

Each run creates a directory under `datadir/tcfmeasure/prefilter-<timestamp>/` with these files:

| File | Content |
| --- | --- |
| `prefilter.sqlite` / `prefilter.csv` | one row per domain with all check results |
| `funnel.csv` | input → HTTP usable → robots allowed → reachable → TCF present → ping → cmpLoaded → gdprApplies |
| `notes.csv` | robots exclusions, robots decisions where urllib differs, bot blocks the browser got past, redirects, duplicates |
| `tcf_sites.csv` | domains with `cmpLoaded` and `gdprApplies`; this is the input for the main measurement |
| `run_metadata.json` | date, IP country, Git commit, browser/geckodriver/Selenium/OpenWPM versions, config, Tranco list |

For comparison, Matte et al. report for .de: 1000 domains → 881 reachable → 56 with a TCF banner (6.4 %).
