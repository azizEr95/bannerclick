"""C) One visit = one variant of one site in a fresh browser profile.

    1. Navigate and stay VISIT_WAIT seconds on the page. The TCF listener is registered as soon
       as __tcfapi exists, every event is recorded.
    2. Snapshot "before" (V1): the last event before any click, plus the TC string found in the
       cookie euconsent-v2 / localStorage; storage_matches_api marks differences between the two.
    3. Action: reject (reject.py), accept or settings (accept.py). Cookiewalls: in the reject
       variant nothing is clicked (only "before" is stored); the accept variant runs normally.
    4. Snapshot "after_action": the event with eventStatus useractioncomplete.
    5. After RELOAD_WAIT seconds reload, snapshot "reload".
    If no event carries the decision, the TC string from cookie/localStorage is stored instead
    (source "cookie", decoded later by tcfmeasure.decode). signal_source says which one the
    visit's signal after the choice comes from: after_action / reload / cookie.

Used by the OpenWPM command (openwpm_command.py), the local test run and the manual mode.
"""
import re
import time
from datetime import datetime, timezone

from selenium.common.exceptions import TimeoutException, WebDriverException

from tcfmeasure import config
from tcfmeasure.accept import Accepter, SettingsViewer
from tcfmeasure.botblock import check_page
from tcfmeasure.reject import Rejecter
from tcfmeasure.tcf_signal import TcfWatcher, tcf_log, wait_for_cmp

EXTRAS_JS = (config.REPO_DIR / "tcfmeasure" / "js" / "page_extras.js").read_text()
TC_STRING = re.compile(r"^C[A-Za-z0-9_-]{20,}(\.[A-Za-z0-9_-]+)*$")
TC_COOKIE_NAMES = ["euconsent-v2", "euconsent"]


def now():
    return datetime.now(timezone.utc).isoformat()


# ---------- Loading and listening ----------

def navigate(driver, url):
    """Starts loading without waiting for the load event, so the listener can be registered
    early (the effect of pageLoadStrategy "eager", which OpenWPM's driver does not use)."""
    driver.execute_script("window.location.href = arguments[0];", url)


def stay_and_listen(driver, seconds):
    """Stays on the page for `seconds` and registers the TCF listener as soon as possible.
    Returns (event log or None, seconds until the listener was registered)."""
    started = time.monotonic()
    listener_seconds = None
    while time.monotonic() - started < seconds:
        if tcf_log(driver) is not None and listener_seconds is None:
            listener_seconds = round(time.monotonic() - started, 1)
            page_extra(driver, "gdpr_consent")  # enlarges the Resource Timing buffer early
        time.sleep(1)
    return tcf_log(driver), listener_seconds


def page_extra(driver, mode):
    try:
        driver.switch_to.default_content()
        return driver.execute_script(EXTRAS_JS, mode)
    except WebDriverException:
        return None


def stored_tc_string(driver):
    """(name, TC string) from the cookie euconsent-v2 (or another cookie / localStorage entry
    that looks like a TC string), or (None, None)."""
    try:
        cookies = driver.get_cookies()
    except WebDriverException:
        cookies = []
    for name in TC_COOKIE_NAMES:
        for cookie in cookies:
            if cookie["name"] == name and cookie["value"]:
                return f"cookie:{name}", cookie["value"]
    for cookie in cookies:
        if TC_STRING.match(cookie["value"] or ""):
            return f"cookie:{cookie['name']}", cookie["value"]
    for entry in page_extra(driver, "storage") or []:
        return entry["name"], entry["value"]
    return None, None


# ---------- Rows ----------

def snapshot_row(visit, phase, event, storage):
    """One tcf_snapshots row from an event (source api) or, without event, from storage (source cookie)."""
    storage_name, stored = storage
    if not event and not stored:
        return None
    row = {
        "visit_id": visit.get("visit_id"), "variant": visit["variant"], "phase": phase,
        "source": "api" if event else "cookie", "time_stamp": now(),
        "storage_name": storage_name, "storage_tc_string": stored,
        "storage_matches_api": (stored == event["tcString"]) if (event and stored) else None,
        "tc_string": event["tcString"] if event else stored,
    }
    if event:
        row.update({
            "event_status": event["eventStatus"], "cmp_status": event["cmpStatus"],
            "gdpr_applies": event["gdprApplies"],
            "purpose_consents": event["purposeConsents"], "purpose_li": event["purposeLegitimateInterests"],
            "vendor_consents": event["vendorConsents"], "vendor_li": event["vendorLegitimateInterests"],
            "special_feature_optins": event["specialFeatureOptins"],
            "publisher_consents": event["publisherConsents"], "publisher_li": event["publisherLegitimateInterests"],
        })
    return row


def event_rows(visit, page, log):
    return [{
        "visit_id": visit.get("visit_id"), "variant": visit["variant"], "page": page, "seq": seq,
        "time_ms": event["time"], "event_status": event["eventStatus"], "cmp_status": event["cmpStatus"],
        "tc_string": event["tcString"], "raw": event["raw"],
    } for seq, event in enumerate(log or [])]


ACTION_FIELDS = ["reject_level", "accept_result", "useractioncomplete", "clicked_labels",
                 "toggles_total", "toggles_preselected", "toggles_deselected", "toggles_failed",
                 "toggle_labels", "screenshots", "note", "cookiewall_reason"]


# ---------- One visit ----------

def run_variant(driver, url, domain, variant, screenshot_prefix, mode, visit_id=None, action=None):
    """action: None = automatic (reject.py/accept.py); for the manual mode a function
    action(driver, watcher) that lets the person click and returns their answers as a dict."""
    visit = {"visit_id": visit_id, "mode": mode, "domain": domain, "url": url, "variant": variant,
             "started_at": now()}
    result = {"visit": visit, "snapshots": [], "events": []}

    navigate(driver, url)
    log, visit["listener_seconds"] = stay_and_listen(driver, config.VISIT_WAIT)
    visit["final_url"] = driver.current_url
    visit["page_title"], visit["bot_blocked"] = check_page(driver)
    visit["tcfapi_found"] = log is not None
    if visit["bot_blocked"]:
        driver.save_screenshot(f"{screenshot_prefix}_bot_blocked.png")
        visit["note"] = "bot-blocked page"
        return result

    before = snapshot_row(visit, "before", log[-1] if log else None, stored_tc_string(driver))
    result["snapshots"] += [before] if before else []
    result["events"] += event_rows(visit, "load", log)

    watcher = TcfWatcher(driver)
    watcher.start()
    if action:
        outcome = action(driver, watcher)
    elif variant == "reject":
        outcome = Rejecter(driver, watcher.is_done, screenshot_prefix).reject()
    elif variant == "accept":
        outcome = Accepter(driver, watcher.is_done, screenshot_prefix).accept()
    else:
        outcome = SettingsViewer(driver, watcher.is_done, screenshot_prefix).view()
    visit.update({key: outcome.get(key) for key in ACTION_FIELDS if key in outcome})
    visit.update({key: value for key, value in outcome.items() if key.startswith("manual_")})
    visit["action_method"] = outcome.get("reject_method")
    visit["cookiewall"] = bool(outcome.get("cookiewall_reason")) or outcome.get("reject_level") == "cookiewall"
    visit["navigated_after_action"] = watcher.navigated

    nothing_clicked = variant == "settings" or visit.get("reject_level") == "cookiewall"
    if nothing_clicked:
        return result

    after_event = watcher.decision()
    action_log = tcf_log(driver) or []
    result["events"] += event_rows(visit, "action", action_log if watcher.navigated else action_log[watcher.events_before:])
    visit["resource_gdpr_consent"] = page_extra(driver, "gdpr_consent") if mode != "crawler" else None

    time.sleep(config.RELOAD_WAIT)
    try:
        driver.refresh()
    except TimeoutException:
        pass
    reload_log = wait_for_cmp(driver, config.RELOAD_CMP_WAIT)
    reload_event = reload_log[-1] if reload_log else None
    result["events"] += event_rows(visit, "reload", reload_log)
    storage = stored_tc_string(driver)

    if after_event:
        result["snapshots"].append(snapshot_row(visit, "after_action", after_event, storage))
    if reload_event:
        result["snapshots"].append(snapshot_row(visit, "reload", reload_event, storage))
    if not after_event and not reload_event and storage[1]:
        result["snapshots"].append(snapshot_row(visit, "after_action", None, storage))
    visit["signal_source"] = ("after_action" if after_event else "reload" if reload_event
                              else "cookie" if storage[1] else None)
    return result


def set_visit_id(result, visit_id):
    for row in [result["visit"], *result["snapshots"], *result["events"]]:
        row["visit_id"] = visit_id
