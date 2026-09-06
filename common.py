"""Shared helpers for the CongressScrapers command-line scripts.

Every script follows the same shape: parse -c/-s style arguments, fetch a
document over HTTP (optionally through a proxy), turn it into plain dicts, and
print the result to stdout as JSON (default) or CSV (--csv). Progress and error
messages go to stderr so stdout stays clean for data. The parts common to all
scripts live here; each script keeps only its site-specific logic.
"""
import argparse
import csv
import json
import sys

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
DEFAULT_TIMEOUT = 30
DEFAULT_CONGRESS = 119


# --------------------------------------------------------------------------- #
# Logging and HTTP
# --------------------------------------------------------------------------- #

def log(message):
    """Print a progress or diagnostic message to stderr."""
    print(message, file=sys.stderr)


def build_proxies(proxy):
    """Turn a single proxy URL into the mapping requests expects, or None."""
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def fetch(url, proxy=None, timeout=DEFAULT_TIMEOUT):
    """GET url and return the response body, or None after logging the failure."""
    log(f"Fetching {url}")
    try:
        response = requests.get(
            url, headers=HEADERS, proxies=build_proxies(proxy), timeout=timeout
        )
    except requests.RequestException as error:
        log(f"Request error: {error}")
        return None

    if response.status_code != 200:
        log(f"Request failed: {response.status_code}")
        if response.status_code == 403:
            log("The site may block non-US IPs; try --proxy with a US exit node.")
        return None
    return response.text


# --------------------------------------------------------------------------- #
# Small conversion helpers
# --------------------------------------------------------------------------- #

def ordinal(number):
    """1 -> '1st', 2 -> '2nd', 103 -> '103rd', 111 -> '111th'."""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def to_int(value, default=None):
    """int(value) when possible, otherwise default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def xml_text(element, path):
    """Stripped text of the first child matching path, or None if absent/empty."""
    child = element.find(path)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def xml_children_to_dict(element, skip=()):
    """Map each direct child's tag to its (stripped) text, skipping given tags.

    Accepts None and returns {} so callers can pass element.find(...) directly.
    """
    if element is None:
        return {}
    return {
        child.tag: child.text.strip() if child.text else child.text
        for child in element
        if child.tag not in skip
    }


# --------------------------------------------------------------------------- #
# Command-line arguments
# --------------------------------------------------------------------------- #

def make_parser(description, session=True):
    """ArgumentParser with the options shared by all scripts.

    Adds -c/--congress, -s/--session (unless session=False), -p/--proxy and
    --csv. Scripts add their own options on top.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-c", "--congress", type=int, default=DEFAULT_CONGRESS,
        help=f"Congress number (default: {DEFAULT_CONGRESS})",
    )
    if session:
        parser.add_argument(
            "-s", "--session", type=int, default=1, choices=(1, 2),
            help="Session number, 1 or 2 (default: 1)",
        )
    parser.add_argument(
        "-p", "--proxy", default=None,
        help="HTTP(S) proxy URL such as http://host:port "
             "(senate.gov and congress.gov may block non-US IPs)",
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Print CSV instead of JSON",
    )
    return parser


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def flatten(record, parent_key=""):
    """Flatten nested dicts into one level for CSV.

    Nested dict keys are joined with '_' ('vote_counts' -> 'vote_counts_yea');
    lists are kept as a JSON string in a single cell.
    """
    flat = {}
    for key, value in record.items():
        full_key = f"{parent_key}_{key}" if parent_key else key
        if isinstance(value, dict):
            flat.update(flatten(value, full_key))
        elif isinstance(value, list):
            flat[full_key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[full_key] = value
    return flat


def print_json(data):
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    print()


def print_csv(rows):
    """Write dict rows as CSV; columns appear in order of first occurrence."""
    rows = [flatten(row) for row in rows]
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def output(data, as_csv=False, to_rows=None):
    """Print data as JSON, or as CSV when as_csv is set.

    For CSV, to_rows converts data into the list of dicts that become rows.
    When omitted, data itself must be a list of dicts or a single dict.
    """
    if not as_csv:
        print_json(data)
        return
    rows = to_rows(data) if to_rows else data
    if isinstance(rows, dict):
        rows = [rows]
    print_csv(rows)
