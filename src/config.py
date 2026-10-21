"""Configuration for SlothPrep data sources."""

SNEHASISHROY_REPO = "snehasishroy/leetcode-companywise-interview-questions"
SNEHASISHROY_RAW_BASE = (
    "https://raw.githubusercontent.com/snehasishroy/"
    "leetcode-companywise-interview-questions/master"
)
SNEHASISHROY_API_CONTENTS = (
    "https://api.github.com/repos/snehasishroy/"
    "leetcode-companywise-interview-questions/contents"
)

TIME_WINDOWS = {
    "thirty-days.csv": {
        "label": "last_30_days",
        "priority": 1,
        "description": "Questions reported in the last 30 days",
    },
    "three-months.csv": {
        "label": "last_3_months",
        "priority": 2,
        "description": "Questions reported in the last 3 months",
    },
    "six-months.csv": {
        "label": "last_6_months",
        "priority": 3,
        "description": "Questions reported in the last 6 months",
    },
    "more-than-six-months.csv": {
        "label": "more_than_6_months",
        "priority": 4,
        "description": "Questions older than 6 months",
    },
    "all.csv": {
        "label": "all_time",
        "priority": 5,
        "description": "All recorded questions for the company",
    },
}

ATTRIBUTION = (
    "Data sourced from community-maintained GitHub repositories "
    "(primarily snehasishroy/leetcode-companywise-interview-questions, "
    "snapshot ~July 2026). These are self-reported / LeetCode-tag based "
    "and are NOT official or guaranteed interview questions. "
    "Always verify with original sources and treat as patterns only."
)

DEFAULT_COMPANY = "google"  # first end-to-end focus
USER_AGENT = "SlothPrep/0.1 (personal research; respectful rate limits)"