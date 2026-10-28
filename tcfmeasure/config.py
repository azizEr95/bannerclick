"""Settings for the tcfmeasure scripts. Every value here is written into run_metadata.json."""
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
LISTS_DIR = REPO_DIR / "tcfmeasure" / "lists"      # filtered Tranco lists (committed for reproducibility)
OUTPUT_DIR = REPO_DIR / "datadir" / "tcfmeasure"   # crawl results

# A) Website selection
TRANCO_TLD = ".de"
TRANCO_TOP_N = 1000

# B) Prefilter crawl
# User agent of the Firefox 121 used by OpenWPM, so that HTTP checks and browser see the same site.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
ACCEPT_LANGUAGES = "de-DE,de"   # Firefox pref intl.accept_languages (German users)
ROBOTS_USER_AGENT = "*"         # robots.txt rules are evaluated for this agent
HTTP_TIMEOUT = 30               # seconds for the HTTP reachability and robots.txt requests
PAGE_LOAD_TIMEOUT = 60          # seconds for the browser page load
TCF_WAIT = 60                   # max seconds to wait for the CMP (same as BannerClick SLEEP_TIME)
TCF_POLL_INTERVAL = 2           # seconds between two __tcfapi('ping') attempts
TCF_CALL_TIMEOUT = 5            # seconds a single __tcfapi call may take
PAUSE_BETWEEN_DOMAINS = 2       # seconds of pause between two domains

# C) Main measurement
VARIANTS = ["reject", "accept", "settings"]   # each in a fresh profile, run in rounds (see crawl.py)
VISIT_WAIT = 60                 # seconds on the page before the action (BannerClick SLEEP_TIME)
RELOAD_WAIT = 3                 # seconds between the decision and the reload (Matte et al.)
RELOAD_CMP_WAIT = 20            # max seconds to wait for the CMP after the reload
COMMAND_TIMEOUT = 300           # OpenWPM timeout for one visit
