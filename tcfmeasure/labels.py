"""Classifies button labels by how much consent they express (Matte et al., Appendix D:
"the button with the least consenting label wins"). Lower rank = less consent.

Word stems are matched at the start of a word, case-insensitive, German and English.
Reject phrases are matched first and removed, so "nicht zustimmen" is a rejection and not
an acceptance.
"""
import re

REJECT_ALL = [
    "alle ablehnen", "alles ablehnen", "alle zwecke ablehnen", "alle abwählen", "alle abwaehlen",
    "alle deaktivieren", "alles deaktivieren", "reject all", "decline all", "deny all", "refuse all",
    "deselect all", "disable all", "object all", "alle widersprechen", "allen widersprechen",
]
REJECT = [
    "ablehnen", "verweigern", "nicht zustimmen", "nicht einverstanden", "nicht akzeptieren",
    "widersprechen", "ohne einwilligung", "ohne zustimmung", "reject", "decline", "deny", "refuse",
    "disagree", "do not agree", "don't agree", "do not accept", "do not consent", "don't consent",
]
NECESSARY_ONLY = [
    "nur notwendige", "nur erforderliche", "nur essenzielle", "nur essentielle", "nur technisch notwendige",
    "nur funktionale", "only necessary", "necessary only", "only essential", "essential only",
    "only required", "strictly necessary only",
]
# Contain an accept word but only save the current selection (e.g. Cookiebot); checked before ACCEPT.
SAVE_SELECTION = ["auswahl erlauben", "auswahl zulassen", "allow selection"]
SAVE = [
    "auswahl speichern", "auswahl bestätigen", "auswahl übernehmen", "einstellungen speichern",
    "speichern", "bestätigen", "übernehmen", "save", "confirm",
]
SETTINGS = [  # "details" is left out: too generic ("Prime Details" on amazon.de)
    "einstellungen", "anpassen", "optionen", "verwalten", "konfigurieren", "präferenzen",
    "individuell", "zwecke anzeigen", "personalisieren", "settings", "preferences", "customize",
    "customise", "options", "configure",
]
SETTINGS_WHOLE_WORDS = ["manage"]  # whole word only, so that "manager magazin" does not match
ACCEPT = [  # word stems; "consent" is left out, it also appears in "manage consent"
    "akzeptier", "zustimm", "stimme zu", "einverstanden", "annehm", "erlaub", "zulass",
    "einwilligen", "willige ein",  # the verb only: "Einwilligung verwalten" stays settings
    "alle auswählen", "mit werbung", "accept", "agree", "allow", "select all", "got it",
]
ACCEPT_WHOLE_WORDS = ["ok", "okay"]  # whole words only, so that "Oktober" does not match

# Options for a single vendor (e.g. the telco ID "Utiq" on many German sites). They do not reject
# purposes, so they count as "other" and are never clicked (vendor options are ignored).
VENDOR_SPECIFIC = ["utiq"]

# Longer labels are descriptions (e.g. the purpose "Speichern von oder Zugriff auf Informationen
# auf einem Endgerät"), not action buttons.
MAX_BUTTON_LABEL = 50

# Rank of each category; ACCEPT is never clicked.
RANK = {"reject_all": 0, "reject": 1, "necessary_only": 2, "save": 3, "settings": 4, "other": 5, "accept": 9}

# "Nur notwendige akzeptieren" contains an accept word but is the reject option on many banners.
# True: it counts as necessary_only (rank: reject < necessary_only < save); the clicked label is
# stored, so the analysis can still tell these cases apart.
ALLOW_ACCEPT_NECESSARY_ONLY = True


def _pattern(phrases, whole_words=False):
    end = r"\b" if whole_words else ""
    return re.compile(r"\b(" + "|".join(re.escape(p) for p in phrases) + r")" + end, re.IGNORECASE)


_REJECT_ALL = _pattern(REJECT_ALL)
_REJECT = _pattern(REJECT)
_NECESSARY_ONLY = _pattern(NECESSARY_ONLY)
_SAVE_SELECTION = _pattern(SAVE_SELECTION)
_SAVE = _pattern(SAVE)
_SETTINGS = _pattern(SETTINGS)
_SETTINGS_WHOLE_WORDS = _pattern(SETTINGS_WHOLE_WORDS, whole_words=True)
_ACCEPT = _pattern(ACCEPT)
_ACCEPT_WHOLE_WORDS = _pattern(ACCEPT_WHOLE_WORDS, whole_words=True)
_VENDOR_SPECIFIC = _pattern(VENDOR_SPECIFIC)


def classify(label):
    """One of: reject_all, reject, necessary_only, save, settings, other, accept."""
    text = " ".join(label.split()).lower()
    without_rejections = _REJECT.sub(" ", _REJECT_ALL.sub(" ", text))
    has_accept = bool(_ACCEPT.search(without_rejections) or _ACCEPT_WHOLE_WORDS.search(without_rejections))

    if has_accept and len(text) > MAX_BUTTON_LABEL:
        return "accept"  # stays excluded, even as a long label
    if len(text) > MAX_BUTTON_LABEL or _VENDOR_SPECIFIC.search(text):
        return "other"
    if _REJECT_ALL.search(text):
        return "reject_all"
    if _REJECT.search(text):
        return "reject"
    if _NECESSARY_ONLY.search(text):
        return "necessary_only" if (ALLOW_ACCEPT_NECESSARY_ONLY or not has_accept) else "accept"
    if _SAVE_SELECTION.search(text):
        return "save"
    if has_accept:
        return "accept"
    if _SAVE.search(text):
        return "save"
    if _SETTINGS.search(text) or _SETTINGS_WHOLE_WORDS.search(text):
        return "settings"
    return "other"


_ALL = re.compile(r"\b(alle|alles|all)\b", re.IGNORECASE)


def accept_all(candidates):
    """For the accept variant: an accept button, preferably one that says "alle"/"all"."""
    accepts = [c for c in candidates if c["category"] == "accept"]
    with_all = [c for c in accepts if _ALL.search(c["label"])]
    return (with_all or accepts or [None])[0]


def least_consenting(candidates, allowed_categories):
    """The candidate with the lowest rank among the allowed categories, or None.
    candidates: list of dicts with a "category" key. Ties keep the page order."""
    allowed = [c for c in candidates if c["category"] in allowed_categories]
    return min(allowed, key=lambda c: RANK[c["category"]]) if allowed else None
