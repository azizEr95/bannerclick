"""Cookiewall check ("Pay or OK"): BannerClick's subscription detection plus German terms.

BannerClick (Rasaii et al. 2023) looks for prices and words like "abo" or "subscribe" in the
banner text. German PUR/contentpass walls often write "PUR-Abo" or "werbefrei", which it misses,
so those terms are added here. Prices written as "3,99 Euro" are checked here as well: that branch
of BannerClick's sub_detection fails ('str' object has no attribute 'visit_id') and returns nothing.
"""
import re

from subscriptiondetection import sub_detection

GERMAN_TERMS = re.compile(
    r"pur[- ]?abo|\bpur\b.*abonnieren|werbefrei|contentpass|freechoice|ohne werbung|abo abschließen|"
    r"\d+[.,]\d{2}\s*euro\b",
    re.IGNORECASE)


def detect(banner_text, banner_html):
    """Returns the reason ("bannerclick" or "german_terms") if the banner is a cookiewall, else None."""
    if not banner_text:
        return None
    if sub_detection(banner_text, banner_html or "<div></div>"):
        return "bannerclick"
    if GERMAN_TERMS.search(banner_text):
        return "german_terms"
    return None
