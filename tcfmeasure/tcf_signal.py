"""Reads the TCF signal of the current page through the listener in js/tcf_listener.js.

The listener lives in the page, so its log is lost when the page navigates. Many CMPs reload or
redirect after the user's choice (e.g. mobile.de). TcfWatcher marks the page before an action;
if the mark is gone afterwards, the page has changed and the action counts as completed as soon
as the new page reports a stored decision (eventStatus tcloaded or useractioncomplete with a
TC string).
"""
import time
import uuid

from selenium.common.exceptions import WebDriverException

from tcfmeasure.config import REPO_DIR

LISTENER_JS = (REPO_DIR / "tcfmeasure" / "js" / "tcf_listener.js").read_text()
SET_MARK_JS = "window.__tcfmeasureMark = arguments[0];"
GET_MARK_JS = "return window.__tcfmeasureMark || null;"


def tcf_log(driver):
    """All events of the current page (registers the listener on first call), or None."""
    try:
        driver.switch_to.default_content()
        return driver.execute_script(LISTENER_JS)
    except WebDriverException:
        return None


def wait_for_cmp(driver, seconds):
    """Polls until the listener delivered a state with cmpStatus loaded; returns the log."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        log = tcf_log(driver)
        if log and any(event["cmpStatus"] == "loaded" for event in log):
            return log
        time.sleep(0.5)
    return tcf_log(driver)


def is_stored_decision(event):
    return event["eventStatus"] in ("tcloaded", "useractioncomplete") and bool(event["tcString"])


class TcfWatcher:
    """Call start() right before the user action, then is_done() until it returns True."""

    def __init__(self, driver):
        self.driver = driver
        self.mark = None
        self.events_before = 0
        self.navigated = False

    def start(self):
        self.mark = uuid.uuid4().hex
        self.events_before = len(tcf_log(self.driver) or [])
        self.navigated = False
        try:
            self.driver.execute_script(SET_MARK_JS, self.mark)
        except WebDriverException:
            pass

    def page_changed(self):
        try:
            return self.driver.execute_script(GET_MARK_JS) != self.mark
        except WebDriverException:
            return True

    def is_done(self):
        if self.page_changed():
            self.navigated = True
            return any(is_stored_decision(event) for event in tcf_log(self.driver) or [])
        new_events = (tcf_log(self.driver) or [])[self.events_before:]
        return any(event["eventStatus"] == "useractioncomplete" for event in new_events)

    def decision(self):
        """The event that carries the user's decision (last useractioncomplete, or after a page
        change the first stored decision of the new page), or None."""
        log = tcf_log(self.driver) or []
        if self.navigated:
            return next((event for event in log if is_stored_decision(event)), None)
        return next((e for e in reversed(log[self.events_before:]) if e["eventStatus"] == "useractioncomplete"), None)
