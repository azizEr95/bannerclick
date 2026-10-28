"""Banner actions of the accept and settings variants, built on the reject logic (reject.py).

Accepter: clicks the accept button on level 1 (preferably "Alle akzeptieren"). Cookiewalls are
    accepted like any other banner, but marked.
SettingsViewer (V3): opens the second layer, takes screenshots of level 1 and 2 and counts the
    preselected purpose switches. Nothing is saved.
"""
import time

from tcfmeasure import cookiewall, labels
from tcfmeasure.reject import LAYER_WAIT, Rejecter, find_controls


def cookiewall_reason(banners):
    for text, html in banners:
        reason = cookiewall.detect(text, html)
        if reason:
            return reason
    return None


class Accepter(Rejecter):
    def finish(self, result, method=None, note=None):
        self.result.update(accept_result=result, reject_level=None, reject_method=method, note=note)
        if result == "unklar":
            self.screenshot(result)
        return self.result

    def accept(self):
        self.screenshot("level1")
        buttons, _, banners = find_controls(self.driver)
        self.result["cookiewall_reason"] = cookiewall_reason(banners)
        button = labels.accept_all(buttons)
        if not button:
            return self.finish("unklar", note="no accept button found")
        self.click_button(button)
        if self.action_completed():
            return self.finish("accepted", "level1_button")
        if not self.banner_present():
            return self.finish("accepted", "level1_button", note="banner closed, but no useractioncomplete")
        return self.finish("unklar", "level1_button", note="banner still there after accept click")


class SettingsViewer(Rejecter):
    def finish(self, result, method=None, note=None):
        self.result.update(reject_level=None, reject_method=method, note=note)
        return self.result

    def view(self):
        self.screenshot("level1")
        buttons, _, banners = find_controls(self.driver)
        self.result["cookiewall_reason"] = cookiewall_reason(banners)
        settings_button = labels.least_consenting(buttons, {"settings"})
        if not settings_button:
            return self.finish(None, note="no settings button on level 1")
        self.click_button(settings_button)
        time.sleep(LAYER_WAIT)
        self.screenshot("level2")
        _, toggles, _ = find_controls(self.driver)
        self.count_toggles(toggles)
        return self.finish(None, "level2_viewed")
