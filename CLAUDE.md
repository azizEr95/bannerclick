Projektkontext

Wir sind ein 2er-Team (Master Medieninformatik, BHT Berlin, Modul „Wissenschaftliches Arbeiten"). Wir machen eine Nachmessung von Matte, Bielova & Santos (2020): „Do Cookie Banners Respect my Choice?" (IEEE S&P 2020, arXiv:1911.09964) für deutsche Websites. Ergebnis ist ein Short Paper (4–6 Seiten, ACM).

Matte nutzte TCF v1.1 (__cmp(), 5 Zwecke) und crawlte 2019 von Frankreich aus.
Heute gilt TCF v2.2 (__tcfapi, 11 Zwecke). Seit v2.2 ist berechtigtes Interesse für die Zwecke 3–6 nicht mehr erlaubt.
Dieses Repo ist ein Fork von BannerClick (Bouhoula et al. 2024, Rasaii et al. 2023), basierend auf OpenWPM. Wir erweitern es um die Messung des TCF-v2.2-Signals.
Das Paper von Matte liegt unter docs/ (falls vorhanden). Methode: Abschnitt IV, Ablauf der manuellen Klicks: Anhang D.
TCF-Spezifikation: https://github.com/InteractiveAdvertisingBureau/GDPR-Transparency-and-Consent-Framework
Arbeitsweise
Vor jeder Änderung: Plan vorschlagen, Rückfragen stellen, auf Bestätigung warten.
Lesbarer Code ist wichtiger als effizienter Code.
BannerClick-Kern so wenig wie möglich ändern. Eigene Logik in ein separates Modul.
Keinen großen Crawl ohne Freigabe starten. Neue Funktionen zuerst an ca. 10 Websites testen.
robots.txt respektieren, Pausen zwischen Anfragen einhalten.
Website-Auswahl
Rangliste: Tranco mit fester List-ID (wird mitgespeichert).
Die ersten N Domains mit Endung .de (N konfigurierbar, Standard 1000), analog zu Matte (1000 pro TLD).
Vergleichswert Matte für .de (Tab. II): 1000 Domains → 881 erreichbar → 56 mit TCF-Banner (6,4 %).
Definitionen der Verstöße (vorläufig, als austauschbare Funktionen umsetzen)
V1 Zustimmung vor der Wahl: Vor jeder Interaktion liegt ein TC-String vor, in dem ≥ 1 Zweck in purpose.consents gesetzt ist.
V2 Keine Ablehnen-Möglichkeit: getrennt erfassen: Ablehnen auf 1. Ebene / nur auf 2. Ebene / gar nicht.
V3 Vorausgewählt: Zwecke oder Vendors sind auf der 2. Ebene vorausgewählt (ggf. manuell über Screenshots bewertet).
V4 Wahl nicht respektiert:
streng: Nach Ablehnen sind alle Zwecke gesetzt, die auch nach Akzeptieren gesetzt sind.
locker: Nach Ablehnen ist ≥ 1 Zweck in purpose.consents gesetzt.
Getrennt erfassen (nicht als V4 zählen): berechtigtes Interesse nach Ablehnen (purpose.legitimateInterests, besonders Zwecke 3–6).
Zusätzlich: TC-String mit Zustimmung in Requests an Dritte (gdpr_consent, GET und POST) nach Ablehnen.
Signal nur nach eventStatus = useractioncomplete auslesen. Nach 3 Sekunden neu laden und erneut auslesen (wie Matte).
Cookiewalls als eigene Kategorie markieren.
Reproduzierbarkeit (nach Demir et al.)

Bei jedem Crawl automatisch protokollieren: Datum, Crawl-Standort/IP-Land, Browser- und OpenWPM-Version, Wartezeiten, Konfiguration, Tranco-List-ID, Git-Commit. Die README erklärt, wie man alles ausführt.