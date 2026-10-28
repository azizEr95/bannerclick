"""OpenWPM command that runs one measurement visit (visit.py) and stores it in the crawl database.
OpenWPM records the HTTP requests (incl. gdpr_consent in GET/POST) and cookies of the same
visit_id in its own tables (http_requests, javascript_cookies)."""
import logging

from openwpm.commands.browser_commands import tab_restart_browser
from openwpm.commands.types import BaseCommand

from tcfmeasure.store import OpenWPMStore, save_visit
from tcfmeasure.visit import run_variant, set_visit_id


class TCFVisitCommand(BaseCommand):
    def __init__(self, url, domain, variant, screenshot_dir):
        self.url = url
        self.domain = domain
        self.variant = variant
        self.screenshot_dir = screenshot_dir
        self.logger = logging.getLogger("openwpm")

    def __repr__(self):
        return f"TCFVisitCommand({self.url}, {self.variant})"

    def execute(self, webdriver, browser_params, manager_params, extension_socket):
        tab_restart_browser(webdriver)
        if extension_socket is not None:
            extension_socket.send(self.visit_id)  # instrumentation records this visit_id

        screenshot_prefix = self.screenshot_dir / f"{self.visit_id}_{self.domain}_{self.variant}"
        try:
            result = run_variant(webdriver, self.url, self.domain, self.variant, screenshot_prefix,
                                 mode="crawler", visit_id=self.visit_id)
        except Exception as e:
            self.logger.exception("TCF visit failed: %s %s", self.url, self.variant)
            result = {"visit": {"mode": "crawler", "domain": self.domain, "url": self.url,
                                "variant": self.variant, "error": repr(e)}, "snapshots": [], "events": []}
        set_visit_id(result, self.visit_id)
        save_visit(OpenWPMStore(manager_params.storage_controller_address), result)
        visit = result["visit"]
        self.logger.info("TCF visit %s %s: reject_level=%s accept=%s signal=%s", self.domain, self.variant,
                         visit.get("reject_level"), visit.get("accept_result"), visit.get("signal_source"))
