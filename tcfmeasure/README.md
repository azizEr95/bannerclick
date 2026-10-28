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
| `funnel.csv` | input → HTTP usable → robots allowed → reachable → not bot-blocked → TCF present → ping → cmpLoaded → gdprApplies |
| `notes.csv` | robots exclusions, robots decisions where urllib differs, bot blocks the browser got past, redirects, duplicates |
| `tcf_sites.csv` | domains with `cmpLoaded` and `gdprApplies`; this is the input for the main measurement |
| `run_metadata.json` | date, IP country, Git commit, browser/geckodriver/Selenium/OpenWPM versions, config, Tranco list |

For comparison, Matte et al. report for .de: 1000 domains → 881 reachable → 56 with a TCF banner (6.4 %).

## C) Main measurement

```bash
python -m tcfmeasure.crawl datadir/tcfmeasure/prefilter-<...>/tcf_sites.csv   # OpenWPM, Linux server
python -m tcfmeasure.local_run <tcf_sites.csv> --limit 5                     # same logic, plain Selenium (tests)
```

Each site is visited once per variant, and every visit uses a fresh profile. The variants run in
rounds: first every site is visited with *reject*, then with *accept*, then with *settings*. That
way the visits to one site are spread out over time, which triggers fewer bot blocks. One visit
([`visit.py`](visit.py)) goes through these steps:

1. Navigate without waiting for the load event, then stay 60 s on the page. The `__tcfapi`
   listener is registered as soon as the API exists ([`js/tcf_listener.js`](js/tcf_listener.js)),
   and every event is stored in `tcf_events`.
2. Snapshot `before` (V1): the last event before any click. Next to it, the TC string from the
   cookie `euconsent-v2` (or localStorage). `storage_matches_api` marks where the two differ.
3. Action:
   - **reject** ([`reject.py`](reject.py), Matte et al. Appendix D): level 1 reject < "only
     necessary" < level 2 ("Alle ablehnen"/"Alle abwählen", otherwise deselect every enabled
     purpose switch, then the least consenting closing button). Labels with an accept word are
     never clicked. The single exception is "Nur notwendige akzeptieren".
     `reject_level` = 1 / 2 / none / cookiewall / unklar.
   - **accept** ([`accept.py`](accept.py)): "Alle akzeptieren" on level 1.
   - **settings**: opens level 2, takes screenshots and counts preselected switches (V3). Nothing
     is saved.
   - **Cookiewalls** ([`cookiewall.py`](cookiewall.py)): in the reject variant nothing is clicked.
     The accept variant runs normally.
4. Snapshot `after_action` from the `useractioncomplete` event. Many CMPs reload the page after
   the choice, so the watcher in [`tcf_signal.py`](tcf_signal.py) notices when that happens.
5. Reload after 3 s, then snapshot `reload`. If no event carries the decision, the TC string from
   cookie/localStorage is stored instead. `signal_source` = `after_action` / `reload` / `cookie`.

Block pages are marked `bot_blocked` ([`botblock.py`](botblock.py)). Requests with
`gdpr_consent` (GET and POST) and TCF cookies are in OpenWPM's `http_requests` and
`javascript_cookies` tables, under the same `visit_id`. The new tables are described in
[`schema.sql`](schema.sql).

## D) Decoding TC strings

```bash
(cd tcfmeasure/tcstring && npm ci)    # once
python -m tcfmeasure.decode datadir/tcfmeasure/crawl-<...>/crawl-data.sqlite
```

Every TC string, whether it came from `__tcfapi` or from cookie/localStorage, is decoded into
`tc_decoded`. The decoder is [@iabtechlabtcf/core](https://github.com/InteractiveAdvertisingBureau/iabtcf-es)
(version pinned in `tcstring/package.json`). It is the IAB Tech Lab's own implementation of the
TCF v2.2 spec and is still maintained.

## Semi-automatic mode and accuracy check

```bash
python -m tcfmeasure.sample <tcf_sites.csv> --n 30          # random sample, seed stored
python -m tcfmeasure.manual <sample.csv>                    # visible Firefox, a person clicks
python -m tcfmeasure.compare <crawl-data.sqlite> <manual tcf.sqlite>
```

[`manual.py`](manual.py) runs the same visit as the crawler, but a person makes the clicks and
answers questions in the terminal: level, number of switches deselected, whether anything was
preselected. [`compare.py`](compare.py) writes `comparison.csv` and `comparison_summary.csv`,
which hold the accuracy of the crawler per field. The steps for the pilot are in
[`PILOT.md`](PILOT.md).
