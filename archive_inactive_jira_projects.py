#!/usr/bin/env python3
"""
archive_inactive_jira_projects.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Archive Jira projects that have seen no activity in the last
six months and notify a Slack channel when the job finishes.

* Requires:  python-dotenv, requests, python-dateutil
* Auth:      Jira – basic auth (email + API token)
             Slack – incoming-webhook URL
* Env vars:  JIRA_EMAIL        –  e.g. "me@example.com"
             JIRA_API_TOKEN    –  token from https://id.atlassian.com/manage-profile/security/api-tokens
             JIRA_DOMAIN       –  <tenant>  (omit ".atlassian.net")
             SLACK_WEBHOOK_URL –  Slack webhook for the target channel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from argparse import ArgumentParser

from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
import dateutil.parser

# --------------------------------------------------------------------------- #
# 1. Configuration & helpers                                                  #
# --------------------------------------------------------------------------- #

load_dotenv()  # pull env vars from .env if present

JIRA_EMAIL        = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN    = os.getenv("JIRA_API_TOKEN")
JIRA_DOMAIN       = os.getenv("JIRA_DOMAIN")       # <tenant>
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

if not all([JIRA_EMAIL, JIRA_API_TOKEN, JIRA_DOMAIN, SLACK_WEBHOOK_URL]):
    sys.exit("❌  One or more required environment variables are missing.")

JIRA_BASE_URL                 = f"https://{JIRA_DOMAIN}.atlassian.net"
JIRA_PROJECT_SEARCH_EP        = f"{JIRA_BASE_URL}/rest/api/3/project/search"
JIRA_SEARCH_JQL_EP            = f"{JIRA_BASE_URL}/rest/api/3/search/jql"   # ← new endpoint
JIRA_PROJECT_ARCHIVE_EP       = f"{JIRA_BASE_URL}/rest/api/3/project/{{id_or_key}}/archive"

DEFAULT_INACTIVE_DAYS = 180   # ≈ 6 months

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS_JSON = {"Accept": "application/json", "Content-Type": "application/json"}

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# --------------------------------------------------------------------------- #
# 2. Business logic                                                           #
# --------------------------------------------------------------------------- #

def find_inactive_projects(inactive_days: int) -> list[dict]:
    """
    Return projects whose newest issue update is older than `inactive_days`.
    Each element → {"id", "key", "name", "last_updated": datetime|None}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)
    inactive: list[dict] = []

    start_at, max_results, total = 0, 50, None
    logging.info("🔍  Scanning projects (cut-off: %s)…", cutoff.date())

    while total is None or start_at < total:
        resp = requests.get(
            JIRA_PROJECT_SEARCH_EP,
            params={"startAt": start_at, "maxResults": max_results},
            headers=HEADERS_JSON,
            auth=auth,
        )
        resp.raise_for_status()
        data = resp.json()

        total = data["total"]
        for project in data["values"]:
            pid, pkey, pname = project["id"], project["key"], project["name"]

            # Build JQL
            jql = f"project={pkey} ORDER BY updated DESC"
            body = {
                "queries": [{
                    "query": jql,
                    "startAt": 0,
                    "maxResults": 1,
                    "fields": ["updated"]
                }]
            }
            i_resp = requests.post(JIRA_SEARCH_JQL_EP, json=body, headers=HEADERS_JSON, auth=auth)
            i_resp.raise_for_status()
            issues = i_resp.json()["results"][0]["issues"]

            if not issues:
                # No issues at all – treat as inactive
                inactive.append({"id": pid, "key": pkey, "name": pname, "last_updated": None})
                continue

            updated_at = dateutil.parser.isoparse(issues[0]["fields"]["updated"])
            if updated_at < cutoff:
                inactive.append({"id": pid, "key": pkey, "name": pname, "last_updated": updated_at})

        start_at += max_results

    logging.info("➡️  Found %d inactive project(s)", len(inactive))
    return inactive


def archive_project(project: dict) -> bool:
    url = JIRA_PROJECT_ARCHIVE_EP.format(id_or_key=project["id"])
    resp = requests.post(url, headers=HEADERS_JSON, auth=auth)
    if resp.status_code == 202:
        logging.info("📦  Archived %-10s (%s)", project["key"], project["name"])
        return True
    logging.warning("⚠️   Could not archive %s – %s", project["key"], resp.text)
    return False


def notify_slack(msg: str) -> None:
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        r.raise_for_status()
        logging.info("✅  Slack notification sent")
    except Exception as exc:
        logging.warning("⚠️   Slack notification failed: %s", exc)

# --------------------------------------------------------------------------- #
# 3. Main driver                                                              #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> None:
    parser = ArgumentParser(description="Archive inactive Jira projects.")
    parser.add_argument("--days", type=int, default=DEFAULT_INACTIVE_DAYS,
                        help=f"Mark project inactive if last update older than N days (default {DEFAULT_INACTIVE_DAYS}).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be archived without actually archiving.")
    args = parser.parse_args(argv)

    inactive = find_inactive_projects(args.days)

    if not inactive:
        notify_slack("🟢 No Jira projects needed archiving – everything is up to date!")
        return

    if args.dry_run:
        listing = "\n".join(
            f"• {p['name']} ({p['key']}) – last update {p['last_updated'].date() if p['last_updated'] else 'never'}"
            for p in inactive
        )
        msg = f"ℹ️  *Dry run*: {len(inactive)} project(s) would be archived:\n{listing}"
        logging.info(msg.replace('*', ''))   # strip MD for console log
        notify_slack(msg)
        return

    archived, failed = [], []
    for p in inactive:
        (archived if archive_project(p) else failed).append(p)

    summary = [f"📦 Archived {len(archived)} project(s) older than {args.days} days."]
    if archived:
        summary.append("\n*Archived:*")
        summary.extend(f"• {p['name']} ({p['key']})" for p in archived)
    if failed:
        summary.append("\n*Failed:*")
        summary.extend(f"• {p['name']} ({p['key']})" for p in failed)

    notify_slack("\n".join(summary))


if __name__ == "__main__":
    main()
