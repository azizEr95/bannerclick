"""Detects bot-block / challenge pages (Akamai, Cloudflare, ...) instead of the real website.
Such pages count as "bot_blocked", not as "no TCF", so they do not distort the numbers."""
import re

BLOCK_TITLE = re.compile(
    r"zugriff verweigert|access denied|just a moment|attention required|request blocked|"
    r"forbidden|captcha|are you a robot|bot verification|pardon our interruption|"
    r"security check|ddos protection|checking your browser",
    re.IGNORECASE)
# Block pages are short; on a short page these words are a strong signal.
BLOCK_TEXT = re.compile(
    r"access denied|zugriff verweigert|captcha|verify you are human|bist du ein mensch|"
    r"request (was )?blocked|reference #|cloudflare ray id|enable javascript and cookies",
    re.IGNORECASE)
SHORT_PAGE = 1500  # characters of visible text

PAGE_TEXT_JS = "return document.body ? document.body.innerText.slice(0, 5000) : '';"


def is_bot_block(title, body_text):
    if title and BLOCK_TITLE.search(title):
        return True
    return bool(body_text) and len(body_text) < SHORT_PAGE and bool(BLOCK_TEXT.search(body_text))


def check_page(driver):
    """(page_title, bot_blocked) of the current page."""
    try:
        driver.switch_to.default_content()
        title = driver.title
        text = driver.execute_script(PAGE_TEXT_JS)
    except Exception:
        return None, False
    return title, is_bot_block(title, text)
