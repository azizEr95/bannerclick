"""Rejects all purposes on a consent banner, following Matte et al. (2020), Appendix D.

Level 1: click the least consenting button among "reject all" / "reject" / "only necessary".
    It only counts as level 1 if the CMP then reports eventStatus = useractioncomplete.
    Labels like "Einstellungen oder ablehnen" open a second layer instead; then we go on with level 2.
    Without such a button, the settings button is clicked to reach level 2.
Level 2:
    a) Click "Alle ablehnen" / "Alle abwählen" if there is one (then save, if that is still needed).
    b) Otherwise deselect every checked, not disabled purpose switch/checkbox that is visible,
       then click the least consenting closing button (reject < only necessary < save).
    Vendor options are not touched: they sit on separate tabs/lists that are not visible on the
    purpose view, and only visible switches are considered.
Never clicked: buttons with an accept label ("akzeptieren", "zustimmen", ...), options for a
single vendor (e.g. "Utiq") and labels longer than 50 characters, see labels.py.
Before anything is clicked, the banner is checked for a cookiewall (cookiewall.py).

Result (reject_level): "1", "2", "none" (no reject and no settings button, but other banner
buttons), "cookiewall" (nothing clicked) or "unklar" (no banner buttons found, or no
useractioncomplete after the clicks).
Screenshots are taken of level 1, level 2 and every unclear case for the manual check.
"""
import json
import time

from selenium.common.exceptions import WebDriverException

from tcfmeasure import cookiewall, labels
from tcfmeasure.config import REPO_DIR

FIND_CONTROLS_JS = (REPO_DIR / "tcfmeasure" / "js" / "find_controls.js").read_text()
IS_CHECKED_JS = """
    const toggle = arguments[0];
    return typeof toggle.checked === 'boolean' ? toggle.checked : toggle.getAttribute('aria-checked') === 'true';
"""
VISIBLE_FRAMES_JS = """
    return Array.from(document.querySelectorAll('iframe, frame'))
        .map((frame, index) => [index, frame.getBoundingClientRect()])
        .filter(([index, rect]) => rect.width >= 50 && rect.height >= 50)
        .map(([index, rect]) => index);
"""

LEVEL1_REJECT = {"reject_all", "reject", "necessary_only"}
LEVEL2_CLOSE = {"reject_all", "reject", "necessary_only", "save"}

ACTION_WAIT = 5        # seconds to wait for useractioncomplete after a closing click
LAYER_WAIT = 2         # seconds to wait for the second layer to appear
TOGGLE_WAIT = 0.3      # seconds between two toggle clicks
FRAME_DEPTH = 2        # how deep nested iframes are searched


# ---------- Frames ----------

def switch_to(driver, path):
    """Switches into the frame given by a path of frame indices; () is the top document."""
    driver.switch_to.default_content()
    try:
        for index in path:
            driver.switch_to.frame(driver.find_elements("css selector", "iframe, frame")[index])
        return True
    except (WebDriverException, IndexError):
        driver.switch_to.default_content()
        return False


def frame_paths(driver):
    """Paths of the top document and all visible (nested) iframes."""
    paths, level = [()], [()]
    for _ in range(FRAME_DEPTH):
        next_level = []
        for path in level:
            if switch_to(driver, path):
                try:
                    next_level += [path + (index,) for index in driver.execute_script(VISIBLE_FRAMES_JS)]
                except WebDriverException:
                    pass
        paths += next_level
        level = next_level
    driver.switch_to.default_content()
    return paths


# ---------- Controls ----------

def find_controls(driver):
    """All visible buttons and toggles in a consent context, in all frames.
    Each control remembers its frame path; buttons get their label category.
    banners: (text, html) of the banner in each frame that has consent buttons."""
    buttons, toggles, banners = [], [], []
    for path in frame_paths(driver):
        if not switch_to(driver, path):
            continue
        try:
            found = driver.execute_script(FIND_CONTROLS_JS)
        except WebDriverException:
            continue
        for button in found["buttons"]:
            buttons.append({**button, "path": path, "category": labels.classify(button["label"])})
        for toggle in found["toggles"]:
            toggles.append({**toggle, "path": path})
        if found["bannerText"]:
            banners.append((found["bannerText"], found["bannerHtml"]))
    driver.switch_to.default_content()
    return buttons, toggles, banners


def without_repeated_labels(buttons):
    """Drops buttons whose label occurs more than once, e.g. one "Widersprechen" per purpose:
    they act on a single item and do not close the banner."""
    counts = {}
    for button in buttons:
        counts[button["label"].lower()] = counts.get(button["label"].lower(), 0) + 1
    return [button for button in buttons if counts[button["label"].lower()] == 1]


def click(driver, path, element):
    """JavaScript click: works for elements covered by overlays or inside custom switches."""
    try:
        switch_to(driver, path)
        driver.execute_script("arguments[0].click();", element)
        return True
    except WebDriverException:
        return False
    finally:
        driver.switch_to.default_content()


def is_checked(driver, toggle):
    try:
        switch_to(driver, toggle["path"])
        return driver.execute_script(IS_CHECKED_JS, toggle["element"])
    except WebDriverException:
        return None
    finally:
        driver.switch_to.default_content()


def wait_until(condition, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.5)
    return condition()


# ---------- Reject ----------

class Rejecter:
    """is_done: function returning True once the CMP reported eventStatus = useractioncomplete.
    screenshot_prefix: path prefix for the screenshots of this visit."""

    def __init__(self, driver, is_done, screenshot_prefix):
        self.driver = driver
        self.is_done = is_done
        self.screenshot_prefix = str(screenshot_prefix)
        self.result = {
            "reject_level": None, "reject_method": None, "useractioncomplete": False, "clicked_labels": [],
            "toggles_total": None, "toggles_preselected": None,
            "toggles_deselected": None, "toggles_failed": None, "toggle_labels": None,
            "screenshots": [], "note": None, "cookiewall_reason": None,
        }

    def screenshot(self, name):
        path = f"{self.screenshot_prefix}_{name}.png"
        try:
            self.driver.switch_to.default_content()
            self.driver.save_screenshot(path)
            self.result["screenshots"].append(path)
        except WebDriverException:
            pass

    def banner_present(self):
        """A banner or second layer always shows an accept, reject or save button. A remaining
        footer link like "Datenschutzeinstellungen" (category settings) does not count."""
        buttons, _, _ = find_controls(self.driver)
        return any(b["category"] in {"accept", "save"} | LEVEL1_REJECT for b in buttons)

    def action_completed(self):
        """Waits for useractioncomplete after a closing click and records whether it came."""
        self.result["useractioncomplete"] = wait_until(self.is_done, ACTION_WAIT)
        return self.result["useractioncomplete"]

    def click_button(self, button):
        self.result["clicked_labels"].append(button["label"])
        return click(self.driver, button["path"], button["element"])

    def finish(self, level, method=None, note=None):
        self.result.update(reject_level=level, reject_method=method, note=note)
        if level in ("none", "unklar"):
            self.screenshot(level)
        return self.result

    def reject(self):
        self.screenshot("level1")
        buttons, _, banners = find_controls(self.driver)
        if not buttons:
            return self.finish("unklar", note="no banner buttons found")

        # Cookiewalls are a category of their own; BannerClick does not reject them either.
        for text, html in banners:
            reason = cookiewall.detect(text, html)
            if reason:
                self.result["cookiewall_reason"] = reason
                self.screenshot("cookiewall")
                return self.finish("cookiewall", note=f"cookiewall ({reason})")

        reject_button = labels.least_consenting(buttons, LEVEL1_REJECT)
        if reject_button:
            self.click_button(reject_button)
            if self.action_completed():
                return self.finish("1", "level1_button")
            if not self.banner_present():
                # Some CMPs (e.g. amazon.de) close the banner but never send useractioncomplete.
                return self.finish("1", "level1_button", note="banner closed, but no useractioncomplete")
            # No useractioncomplete and the banner is still there: the button opened a second layer.
        else:
            settings_button = labels.least_consenting(buttons, {"settings"})
            if not settings_button:
                return self.finish("none", note="neither reject nor settings button")
            self.click_button(settings_button)

        time.sleep(LAYER_WAIT)
        return self.reject_on_level2()

    def reject_on_level2(self):
        self.screenshot("level2")
        buttons, toggles, _ = find_controls(self.driver)
        self.count_toggles(toggles)

        reject_all = labels.least_consenting(without_repeated_labels(buttons), {"reject_all"})
        if reject_all:
            self.click_button(reject_all)
            if self.action_completed():
                return self.finish("2", "level2_reject_all")
            # "Alle abwählen" only switched everything off; the selection still has to be saved.
            buttons, _, _ = find_controls(self.driver)
            return self.close_level2(buttons, "level2_reject_all_then_save", exclude=reject_all["label"])

        self.deselect(toggles)
        self.screenshot("level2_deselected")
        buttons, _, _ = find_controls(self.driver)
        return self.close_level2(buttons, "level2_deselect")

    def count_toggles(self, toggles):
        enabled = [toggle for toggle in toggles if not toggle["disabled"]]
        self.result["toggles_total"] = len(enabled)
        self.result["toggles_preselected"] = sum(1 for toggle in enabled if toggle["checked"])
        self.result["toggle_labels"] = json.dumps(
            [{"label": t["label"], "checked": t["checked"], "disabled": t["disabled"]} for t in toggles],
            ensure_ascii=False)

    def deselect(self, toggles):
        deselected = failed = 0
        for toggle in toggles:
            if toggle["disabled"] or not toggle["checked"]:
                continue
            click(self.driver, toggle["path"], toggle["clickTarget"])
            time.sleep(TOGGLE_WAIT)
            if is_checked(self.driver, toggle) is False:
                deselected += 1
            else:
                failed += 1
        self.result["toggles_deselected"] = deselected
        self.result["toggles_failed"] = failed

    def close_level2(self, buttons, method, exclude=None):
        candidates = [b for b in without_repeated_labels(buttons) if b["label"] != exclude]
        close_button = labels.least_consenting(candidates, LEVEL2_CLOSE)
        if not close_button:
            return self.finish("unklar", method, note="no closing button without accept label on level 2")
        self.click_button(close_button)
        if self.action_completed():
            return self.finish("2", method)
        return self.finish("unklar", method, note="no useractioncomplete after closing level 2")
