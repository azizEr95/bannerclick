# Pilot – Anleitung

Ziel: die ganze Kette an den ersten 100 `.de`-Domains testen und die Genauigkeit des Crawlers an
einer Zufallsstichprobe von 30 TCF-Seiten bestimmen. Der automatische Teil läuft auf dem
Linux-Server (Standort Deutschland), der halbautomatische Teil auf dem Mac.

Zeitbedarf, grob geschätzt:

- Vorfilter: ca. 1 h für 100 Domains
- Crawl: ca. 1,5–2 min pro Seite und Variante. Bei 30–45 TCF-Seiten und 3 Varianten sind das 3–5 h.
- Manuell: ca. 2 min pro Seite und Variante. Bei 30 Seiten und 2 Varianten sind das etwa 2 h.

Crawl und manuelle Prüfung sollten **am selben Tag** laufen, weil sich Banner ändern.

## 1. Server einrichten (einmalig)

```bash
git clone git@github.com:azizEr95/bannerclick.git && cd bannerclick   # bzw. git pull
./install.sh                                  # conda-Env "openwpm", Firefox 121, Extension
conda activate openwpm
pip install -r tcfmeasure/requirements.txt    # selenium (schon da), protego, tldextract, bs4
(cd tcfmeasure/tcstring && npm ci)            # @iabtechlabtcf/core zum Dekodieren
```

Lange Läufe in `tmux` (oder `screen`) starten, damit sie ein Abmelden überleben:
`tmux new -s pilot`. Später kommt ihr mit `tmux attach -t pilot` zurück.

## 2. Websites auswählen (A)

```bash
python -m tcfmeasure.tranco_de
```

Das Skript nimmt die aktuelle Tranco-Tagesliste und gibt die List-ID aus. Die Liste landet in
`tcfmeasure/lists/tranco_<ID>_de_top1000.csv`. Committet `tcfmeasure/lists/`, denn die Liste
gehört zur Reproduzierbarkeit.

## 3. Vorfilter (B), erste 100 Domains

```bash
python -m tcfmeasure.prefilter tcfmeasure/lists/tranco_<ID>_de_top1000.csv --limit 100
```

Ergebnis: `datadir/tcfmeasure/prefilter-<Zeitstempel>/`

- `funnel.csv`: Trichter (Eingabe → … → nicht bot-blocked → TCF → cmpLoaded → gdprApplies)
- `notes.csv`: robots.txt-Unterschiede zu urllib, Bot-Sperren, Weiterleitungen, Duplikate
- `tcf_sites.csv`: Eingabe für den Crawl

Kurz prüfen: Wie viele Domains sind `bot_blocked`? Wenn es mehr als eine Handvoll sind, Bescheid geben.

```bash
sqlite3 -header -column datadir/tcfmeasure/prefilter-<...>/prefilter.sqlite \
  "select domain, http_status, page_title from prefilter where bot_blocked = 1"
```

## 4. Stichprobe ziehen

```bash
python -m tcfmeasure.sample datadir/tcfmeasure/prefilter-<...>/tcf_sites.csv --n 30
```

Ergebnis: `sample_30_seed<Seed>.csv` (der Seed steht auch in der `.json`). Die CSV auf den Mac kopieren:

```bash
scp server:bannerclick/datadir/tcfmeasure/prefilter-<...>/sample_30_seed<Seed>.* ./
```

## 5. Crawl (C) auf dem Server

```bash
python -m tcfmeasure.crawl datadir/tcfmeasure/prefilter-<...>/tcf_sites.csv --num-browsers 1
python -m tcfmeasure.decode datadir/tcfmeasure/crawl-<...>/crawl-data.sqlite        # D, danach
```

Der Crawl läuft alle TCF-Seiten in drei Runden durch: erst alle „ablehnen“, dann alle
„akzeptieren“, dann alle „einstellungen“. Jeder Besuch bekommt ein frisches Profil. Den
Fortschritt seht ihr in `datadir/tcfmeasure/crawl-<...>/openwpm.log` (`grep "TCF visit"`).

Kurzer Check nach dem Lauf:

```bash
sqlite3 -header -column datadir/tcfmeasure/crawl-<...>/crawl-data.sqlite "
  select variant, reject_level, accept_result, signal_source, count(*) as n
  from tcf_visits group by 1,2,3,4;
  select count(*) as errors from tcf_visits where error is not null;"
```

## 6. Halbautomatischer Modus (C5) auf dem Mac, parallel zum Crawl

Einmalig einrichten:

```bash
cd bannerclick
python3 -m venv venv && venv/bin/pip install -r tcfmeasure/requirements.txt
(cd tcfmeasure/tcstring && npm ci)
# Firefox 121:     https://archive.mozilla.org/pub/firefox/releases/121.0/mac/en-US/  (DMG öffnen, Firefox.app z. B. nach ~/tcf-tools/)
# geckodriver 0.33: https://github.com/mozilla/geckodriver/releases/tag/v0.33.0 (macos-aarch64)
export TCF_FIREFOX=~/tcf-tools/Firefox.app/Contents/MacOS/firefox
export TCF_GECKODRIVER=~/tcf-tools/geckodriver
```

Starten:

```bash
venv/bin/python -m tcfmeasure.manual sample_30_seed<Seed>.csv
```

Für jede Seite und Variante öffnet sich ein Firefox mit frischem Profil. Das Skript wartet 60 s,
genau wie der Crawler. **In dieser Zeit noch nicht klicken.** Danach erscheint im Terminal die
Anweisung. Ihr klickt im Browser (Ablehnen nach Anhang D, die Regeln stehen im Terminal),
drückt Enter und beantwortet die Fragen: Ebene, Anzahl abgewählter Schalter, vorausgewählt,
Notiz. Das Skript liest das Signal, lädt nach 3 s neu und liest erneut aus.

Abgebrochen? Mit `--output-dir datadir/tcfmeasure/manual-<...>` geht es dort weiter, wo es aufgehört hat.

Wichtig für die Vergleichbarkeit:

- Bei einer Cookiewall nichts klicken, „cookiewall“ antworten.
- Nie mit „Akzeptieren/Zustimmen“ schließen. Einzige Ausnahme: „Nur notwendige akzeptieren“.
- Vendor-Listen nicht anfassen, nur Zweck-Schalter.

## 7. Vergleich Crawler vs. manuell

Die Crawl-Datenbank auf den Mac kopieren (oder umgekehrt) und dann vergleichen:

```bash
venv/bin/python -m tcfmeasure.compare crawl-data.sqlite datadir/tcfmeasure/manual-<...>/tcf.sqlite
```

Das ergibt `comparison.csv` (pro Seite, Variante und Feld: Crawler, manuell, Übereinstimmung)
und `comparison_summary.csv` (Genauigkeit pro Feld).

## 8. Was ich zur Auswertung brauche

- `datadir/tcfmeasure/prefilter-<...>/` (ohne die `.sqlite` geht es auch, die CSVs reichen)
- `datadir/tcfmeasure/crawl-<...>/` komplett (`crawl-data.sqlite`, `screenshots/`, `openwpm.log`, `run_metadata.json`)
- `datadir/tcfmeasure/manual-<...>/` komplett, dazu `comparison*.csv`
- die verwendete List-ID bzw. den Commit von `tcfmeasure/lists/`
