"""Starts a plain Selenium Firefox (without OpenWPM) with a fresh, temporary profile."""
import os

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

from tcfmeasure import config

# Firefox 121 installed by OpenWPM's install.sh; used when no other binary is given.
OPENWPM_FIREFOX = config.REPO_DIR / "firefox-bin" / "firefox"


def firefox_binary(binary=None):
    """Explicit binary > $TCF_FIREFOX > OpenWPM's firefox-bin > Firefox found by Selenium."""
    binary = binary or os.environ.get("TCF_FIREFOX")
    if binary:
        return binary
    if OPENWPM_FIREFOX.exists():
        return str(OPENWPM_FIREFOX)
    return None


def start_firefox(binary=None, geckodriver=None, headless=True):
    options = Options()
    if headless:
        options.add_argument("-headless")
    binary = firefox_binary(binary)
    if binary:
        options.binary_location = binary
    options.set_preference("general.useragent.override", config.USER_AGENT)

    geckodriver = geckodriver or os.environ.get("TCF_GECKODRIVER")
    service = Service(executable_path=geckodriver) if geckodriver else Service()
    driver = webdriver.Firefox(options=options, service=service)
    driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(config.TCF_CALL_TIMEOUT + 5)
    return driver


def browser_versions(driver):
    capabilities = driver.capabilities
    return {
        "browser_name": capabilities.get("browserName"),
        "browser_version": capabilities.get("browserVersion"),
        "geckodriver_version": capabilities.get("moz:geckodriverVersion"),
        "platform": capabilities.get("platformName"),
        "user_agent": driver.execute_script("return navigator.userAgent"),
    }
