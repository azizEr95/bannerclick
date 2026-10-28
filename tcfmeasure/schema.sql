/* Tables of the TCF measurement (tcfmeasure). Used by the OpenWPM crawl (loaded by
 * BCSQLiteStorageProvider next to openwpm/storage/schema.sql), the local test run and the
 * semi-automatic mode. Lists of IDs are stored as JSON arrays, e.g. "[1, 3, 4]".
 */

/* One row per visit = one variant (reject / accept / settings) of one site in a fresh profile. */
CREATE TABLE IF NOT EXISTS tcf_visits (
    visit_id INTEGER,
    mode TEXT,                      -- crawler / local / manual
    domain TEXT,
    url TEXT,
    final_url TEXT,
    variant TEXT,                   -- reject / accept / settings
    started_at TEXT,
    page_title TEXT,
    bot_blocked BOOLEAN,
    tcfapi_found BOOLEAN,
    listener_seconds REAL,          -- seconds after navigation until the TCF listener was registered
    cookiewall BOOLEAN,
    cookiewall_reason TEXT,
    reject_level TEXT,              -- reject variant: 1 / 2 / none / cookiewall / unklar
    accept_result TEXT,             -- accept variant: accepted / unklar
    action_method TEXT,
    useractioncomplete BOOLEAN,
    navigated_after_action BOOLEAN,
    signal_source TEXT,             -- where the signal after the choice comes from: after_action / reload / cookie
    clicked_labels TEXT,            -- JSON list of the clicked button labels
    toggles_total INTEGER,          -- level 2: enabled, visible purpose switches
    toggles_preselected INTEGER,    -- ... of which checked before any click (V3)
    toggles_deselected INTEGER,
    toggles_failed INTEGER,
    toggle_labels TEXT,             -- JSON
    resource_gdpr_consent TEXT,     -- local/manual mode only: GET requests with gdpr_consent (top frame, Resource Timing)
    manual_level TEXT,              -- manual mode: answers of the person who clicked
    manual_deselected INTEGER,
    manual_preselected TEXT,        -- ja / nein / nicht angesehen
    manual_note TEXT,
    note TEXT,
    screenshots TEXT,               -- JSON list of file paths
    error TEXT
);

/* The TCF signal at one point in time of a visit. */
CREATE TABLE IF NOT EXISTS tcf_snapshots (
    visit_id INTEGER,
    variant TEXT,
    phase TEXT,                     -- before / after_action / reload
    source TEXT,                    -- api (__tcfapi event) / cookie (TC string from cookie or localStorage)
    time_stamp TEXT,
    event_status TEXT,
    cmp_status TEXT,
    gdpr_applies BOOLEAN,
    tc_string TEXT,
    purpose_consents TEXT,
    purpose_li TEXT,
    vendor_consents TEXT,
    vendor_li TEXT,
    special_feature_optins TEXT,
    publisher_consents TEXT,
    publisher_li TEXT,
    storage_name TEXT,              -- e.g. cookie euconsent-v2 / localStorage key
    storage_tc_string TEXT,
    storage_matches_api BOOLEAN     -- TC string in storage == TC string reported by __tcfapi
);

/* Every __tcfapi('addEventListener') event that was received. */
CREATE TABLE IF NOT EXISTS tcf_events (
    visit_id INTEGER,
    variant TEXT,
    page TEXT,                      -- load (page before the action) / action (after the action) / reload
    seq INTEGER,
    time_ms INTEGER,
    event_status TEXT,
    cmp_status TEXT,
    tc_string TEXT,
    raw TEXT
);

/* D) Decoded TC strings (python -m tcfmeasure.decode), one row per distinct string. */
CREATE TABLE IF NOT EXISTS tc_decoded (
    tc_string TEXT PRIMARY KEY,
    error TEXT,
    version INTEGER,
    created TEXT,
    last_updated TEXT,
    cmp_id INTEGER,
    cmp_version INTEGER,
    consent_screen INTEGER,
    consent_language TEXT,
    vendor_list_version INTEGER,
    policy_version INTEGER,
    is_service_specific BOOLEAN,
    purpose_one_treatment BOOLEAN,
    publisher_cc TEXT,
    purpose_consents TEXT,
    purpose_li TEXT,
    special_feature_optins TEXT,
    vendor_consents TEXT,
    vendor_li TEXT,
    publisher_consents TEXT,
    publisher_li TEXT,
    vendors_disclosed TEXT,
    decoder TEXT
);
