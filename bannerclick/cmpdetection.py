import time
from selenium.common.exceptions import TimeoutException, JavascriptException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.firefox.options import Options
from selenium import webdriver
import pandas as pd
import urllib.request
import json


from bannerclick.bannerdetection import MyExceptionLogger

try:
    from .config import *
except:
    from config import *


def has___cmp():
    global driver
    try:
        res = driver.execute_script('if (__cmp) return true;', None)
    except JavascriptException as e:
        # print('__tcfapi not found: ', e)
        return False
    except TimeoutException:
        # print("Timeout while probing for __tcfapi.")
        return False
    return True


def has___tcfapi():
    global driver
    try:
        res = driver.execute_script('if (__tcfapi) return true;', None)
    except JavascriptException as e:
        # print('__tcfapi not found: ', e)
        return False
    except TimeoutException:
        # print("Timeout while probing for __tcfapi.")
        return False
    return True


def has___tcfapiLocator():
    locator_list = get___tcfapiLocator()
    return bool(locator_list)


def get___tcfapiLocator():
    global driver
    return driver.find_elements(By.XPATH, "//iframe[contains(@name, '__tcfapiLocator')]")


TCF_TIMEOUT = 5  # seconds to wait for the CMP to answer a __tcfapi call


def run_tcfapi_async(js_body, timeout=TCF_TIMEOUT):
    """Run js_body as an async script. js_body must call done(result) exactly once;
    it is also given up after timeout seconds and then yields None."""
    global driver
    result = None
    old_timeout = None
    try:
        old_timeout = driver.timeouts.script
    except Exception:
        pass
    try:
        driver.set_script_timeout(timeout + 1)
        result = driver.execute_async_script("""
            const done = arguments[arguments.length - 1];
            if (typeof __tcfapi !== 'function') { done(null); return; }
            const timer = setTimeout(() => done(null), %d);
            const finish = (res) => { clearTimeout(timer); done(res); };
            %s
        """ % (timeout * 1000, js_body))
    except JavascriptException as e:
        # print("Exception while calling __tcfapi(): %s" % e)
        pass
    except TimeoutException as e:
        # print("Timeout exception while calling __tcfapi(): %s" % e)
        pass
    finally:
        if old_timeout is not None:
            try:
                driver.set_script_timeout(old_timeout)
            except Exception:
                pass
    return result


def get_TCData():
    """Read the current TCF signal via __tcfapi('addEventListener'), which replaces the
    deprecated getTCData since TCF v2.2. The listener fires right away with the current state.
    Consent maps are reduced to comma-separated lists of the IDs that are true."""
    return run_tcfapi_async("""
        const ids = (o) => o ? Object.keys(o).filter(k => o[k] === true).join(',') : null;
        __tcfapi('addEventListener', 2, (tcData, success) => {
            if (!success || !tcData) { finish(null); return; }
            if (tcData.listenerId !== undefined && tcData.listenerId !== null) {
                try { __tcfapi('removeEventListener', 2, () => {}, tcData.listenerId); } catch (e) {}
            }
            const purpose = tcData.purpose || {};
            const vendor = tcData.vendor || {};
            finish({
                tc_string: tcData.tcString || null,
                tcf_gdpr_applies: tcData.gdprApplies === undefined ? null : tcData.gdprApplies,
                tcf_event_status: tcData.eventStatus || null,
                tcf_cmp_status: tcData.cmpStatus || null,
                tcf_policy_version: tcData.tcfPolicyVersion === undefined ? null : tcData.tcfPolicyVersion,
                tcf_cmp_id: tcData.cmpId === undefined ? null : tcData.cmpId,
                tcf_purpose_consents: ids(purpose.consents),
                tcf_purpose_li: ids(purpose.legitimateInterests),
                tcf_vendor_consents: ids(vendor.consents),
                tcf_vendor_li: ids(vendor.legitimateInterests),
            });
        });
    """)


def get_pingReturn():
    return run_tcfapi_async("""
        __tcfapi('ping', 2, (pingReturn) => finish(pingReturn || null));
    """)


def extract_CMP_list_from_server():
    global driver
    iab_url = "https://iabeurope.eu/cmp-list/"
    driver.get(iab_url)
    driver.find_element(
        By.XPATH, "//*[contains(text(), 'TCF v2.0 CMP Service')]").click()
    select_element = driver.find_element_by_name('tablepress-26_length')
    # actions = ActionChains(driver)
    # actions.move_to_element(select_element).perform()
    # driver.execute_script("arguments[0].scrollIntoView();", select_element)
    # select_element.click()
    driver.execute_script("window.scrollTo(0,window.innerHeight)")
    select = Select(select_element)
    select.select_by_value('100')
    html = driver.page_source
    df_list = pd.read_html(html)
    CMPlist_service = df_list[0]
    CMPlist_service['pv'] = False
    driver.find_element(
        By.XPATH, "//*[contains(text(), 'TCF v2.0 CMP Service')]").click()

    driver.find_element(
        By.XPATH, "//*[contains(text(), 'TCF v2.0 CMP Private (own use)')]").click()
    select_element = driver.find_element_by_name('tablepress-78_length')
    select = Select(select_element)
    select.select_by_value('100')
    html = driver.page_source
    df_list = pd.read_html(html)
    CMPlist_private = df_list[3]
    CMPlist_private['pv'] = True

    CMPlist = pd.concat([CMPlist_service, CMPlist_private], ignore_index=True)
    CMPlist.to_csv('cmp_list.csv')
    print("CMP list is extracted from IAB server")
    return CMPlist


def extract_CMP_list_from_url():
    CMP_list_url = "https://cmp-list.consensu.org/v2/cmp-list.json"
    with urllib.request.urlopen(CMP_list_url) as url:
        CMPlist = json.loads(url.read().decode())['cmps']
    print("CMP list is loaded from url")
    return CMPlist


def get_CMP_list():
    global CMP_list
    if CMP_list is None:
        if EXTRACT_JSON:
            CMP_list = extract_CMP_list_from_url()
        else:
            CMP_list = extract_CMP_list_from_server()
    return CMP_list


def set_CMP_list(CMPlist=None):
    global CMP_list
    if CMP_list is None:
        if CMPlist is None:
            if EXTRACT_JSON:
                CMPlist = extract_CMP_list_from_url()
            else:
                CMPlist = extract_CMP_list_from_server()
        else:
            CMP_list = CMPlist


def get_CMP_id():
    global driver
    ping_return = get_pingReturn()
    if ping_return:
        return ping_return.get("cmpId")
    return None


def get_CMP_name_by_id(cmp_id):
    global driver
    cmp_name = None
    cmps = get_CMP_list()
    if EXTRACT_JSON:
        row = cmps.get(cmp_id)
        if row:
            cmp_name = row["name"]
    else:
        row = cmps.loc[cmps['ID'] == cmp_id]
        if not row.empty:
            cmp_name = row.iloc[0]["Company Name"]
    return cmp_name


def get_CMP_name():
    global driver
    cmp_id = get_CMP_id()
    return get_CMP_name_by_id(cmp_id)


def is_CMP_pv(cmp_id):
    global driver
    pv = False
    cmps = get_CMP_list()
    if EXTRACT_JSON:
        row = cmps.get(cmp_id)
        if row:
            pv = not row["isCommercial"]
    else:
        row = cmps.loc[cmps['ID'] == cmp_id]
        if not row.empty:
            pv = row.iloc[0]["pv"]
    return pv


def log_ConsentData():
    global driver
    try:
        driver.execute_script(
            '__cmp("getConsentData", null, function(val, success) { console.log("sc-consentData=",val.consentData); console.log("sc-metadata=", val.metadata)}); __cmp("getVendorConsents", null, function(val, success) { console.log("sc-consentData-vendorConsents=",val.consentData); console.log("sc-metadata-vendorConsents=", val.metadata)});',
            None)
    except JavascriptException as e:
        print("Exception while calling __cmp(): %s" % e)
    except TimeoutException as e:
        print("Timeout exception while calling __cmp(): %s" % e)


def extract_CMP_data(CMP_raw_dict):
    try:
        visit_db.loc[visit_db.shape[0]-1,
                     CMP_raw_dict.keys()] = CMP_raw_dict.values()
        # if v_id:
        #     CMP_raw_dict['visit_id'] = v_id
        # sql_store_handler("visits", CMP_raw_dict)
        return CMP_raw_dict
    except Exception as ex:
        print("failed to continue extracting CMP data for domain: " + ex.__str__())
        return CMP_raw_dict


def get_info(entry, used_re, display_string):
    matches = used_re.search(str(entry["message"]))
    if matches is not None:
        data = matches.group(1)
        if display_string != "":
            print(display_string + ": " + data)
        return data
    return None


def get_database():
    global visit_db
    return visit_db


def set_database(db=None):
    global visit_db
    if db is None:
        visit_db = pd.DataFrame({
            'visit_id': pd.Series([], dtype='int'),
            'domain': pd.Series([], dtype='str'),
            'url': pd.Series([], dtype='str'),
            'status': pd.Series([], dtype='int'),
            'lang': pd.Series([], dtype='str'),
            'banners': pd.Series([], dtype='int'),
            '__cmp': pd.Series([], dtype='bool'),
            '__tcfapi': pd.Series([], dtype='bool'),
            '__tcfapiLocator': pd.Series([], dtype='bool'),
            'cmp_id': pd.Series([], dtype='int'),
            'cmp_name': pd.Series([], dtype='str'),
            'pv': pd.Series([], dtype='bool'),
            'tc_string': pd.Series([], dtype='str'),
            'tcf_gdpr_applies': pd.Series([], dtype='object'),
            'tcf_event_status': pd.Series([], dtype='str'),
            'tcf_cmp_status': pd.Series([], dtype='str'),
            'tcf_policy_version': pd.Series([], dtype='object'),
            'tcf_purpose_consents': pd.Series([], dtype='str'),
            'tcf_purpose_li': pd.Series([], dtype='str'),
            'tcf_vendor_consents': pd.Series([], dtype='str'),
            'tcf_vendor_li': pd.Series([], dtype='str'),
        })
    else:
        visit_db = db
    return visit_db


TCDATA_KEYS = ['tc_string', 'tcf_gdpr_applies', 'tcf_event_status', 'tcf_cmp_status', 'tcf_policy_version',
               'tcf_purpose_consents', 'tcf_purpose_li', 'tcf_vendor_consents', 'tcf_vendor_li']


def detect_cmp(CMP):
    CMP["__cmp"] = has___cmp()
    CMP["__tcfapi"] = has___tcfapi()
    CMP["__tcfapiLocator"] = has___tcfapiLocator()
    CMP["cmp_id"] = get_CMP_id()
    if CMP["__tcfapi"]:
        tc_data = get_TCData() or {}
        for key in TCDATA_KEYS:
            CMP[key] = tc_data.get(key)
        if CMP["cmp_id"] is None:
            CMP["cmp_id"] = tc_data.get("tcf_cmp_id")
    CMP["cmp_name"] = get_CMP_name_by_id(str(CMP["cmp_id"]))
    CMP["pv"] = is_CMP_pv(str(CMP["cmp_id"]))


def run_cmp_detection():
    CMP = {}
    try:
        detect_cmp(CMP)
    except Exception as ex:
        pass
        # with open(log_file, 'a+') as f:
            # print("failed to continue detecting CMP for domain: " +
            #       " " + ex.__str__(), file=f)
            # MyExceptionLogger(err=ex, file=f)
    return CMP


def run_webdriver():
    options = Options()
    profile = webdriver.FirefoxProfile(
        r'C:\Users\TwilighT\AppData\Roaming\Mozilla\Firefox\Profiles\dfv21ryp.cookiesprofile')
    # options.headless = True
    driver = webdriver.Firefox(
        options=options, firefox_profile=profile, executable_path="./geckodriver.exe")
    driver.maximize_window()
    return driver


def set_webdriver(web_driver=None):
    global driver
    try:
        if web_driver is None:
            web_driver = run_webdriver()
        if driver != webdriver:
            driver = web_driver
            try:
                driver.maximize_window()
            except Exception as ex:
                pass
                # with open(log_file, 'a+') as f:
                    # print(
                    #     f"failed in cd.set_webdriver first time: f{ex.__str__()}", file=f)
                    # MyExceptionLogger(err=ex, file=f)
                    # time.sleep(2)
                    # try:
                    #     driver.maximize_window()
                    # except Exception as ex:
                        # print(
                        #     f"failed in cd.set_webdriver second time: f{ex.__str__()}", file=f)
                        # MyExceptionLogger(err=ex, file=f)
    except Exception as ex:
        # with open(log_file, 'a+') as f:
        #     print(f"failed in cd.set_webdriver: f{ex.__str__()}", file=f)
        #     MyExceptionLogger(err=ex, file=f)
        pass
    return driver


def init(web_driver=None, db=None):  # initialize cmpdetection by setting webdriver instance and database
    global driver
    if web_driver is None:
        driver = run_webdriver()
    else:
        driver = web_driver
    # set_database(db)
    set_CMP_list()