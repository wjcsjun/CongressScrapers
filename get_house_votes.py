"""Scrape US House roll-call votes from clerk.house.gov.

Without --rollcall: list the most recent votes of a session (newest first).
With --rollcall N:  fetch the full record of one vote, including how every
                    member voted.
"""
import re
import sys
import time
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from common import fetch, make_parser, ordinal, output, xml_children_to_dict

MAX_EMPTY_PAGES = 5   # retries when a list page comes back empty or fails
PAGE_DELAY = 2        # seconds between list-page requests

# clerk.house.gov labels tallies differently per vote type: Yea-And-Nay votes
# say "yea"/"nay", Recorded Votes say "Aye"/"No". Normalise to one vocabulary.
COUNT_LABELS = {
    "yea": "yea", "aye": "yea",
    "nay": "nay", "no": "nay",
    "present": "present",
    "not voting": "not_voting",
}


def congress_first_year(congress):
    """Calendar year of a Congress's first session (the 1st Congress met in 1789)."""
    return 1789 + 2 * (congress - 1)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def parse_vote_xml(xml_string):
    """Convert a clerk.house.gov roll-call XML document into a dict."""
    root = ET.fromstring(xml_string)
    metadata = root.find("vote-metadata")
    totals = metadata.find("vote-totals")

    votes = []
    for recorded in root.find("vote-data").findall("recorded-vote"):
        legislator = recorded.find("legislator")
        votes.append({
            "name": legislator.text,
            "name_id": legislator.get("name-id"),
            "party": legislator.get("party"),
            "state": legislator.get("state"),
            "role": legislator.get("role"),
            "vote": recorded.find("vote").text,
        })

    return {
        "metadata": xml_children_to_dict(metadata, skip=("vote-totals",)),
        "party_totals": [
            xml_children_to_dict(party) for party in totals.findall("totals-by-party")
        ],
        "vote_totals": xml_children_to_dict(
            totals.find("totals-by-vote"), skip=("total-stub",)
        ),
        "votes": votes,
    }


def parse_vote_list_html(html):
    """Extract vote summaries from a clerk.house.gov vote-list HTML fragment."""
    soup = BeautifulSoup(html, "html.parser")
    return [parse_vote_entry(entry) for entry in soup.find_all("div", class_="role-call-vote")]


def parse_vote_entry(entry):
    vote = {}

    roll_call_link = entry.select_one("div.heading a")
    if roll_call_link:
        vote["roll_call_number"] = roll_call_link.text.strip()
        if roll_call_link.get("href"):
            vote["detail_url"] = f"https://clerk.house.gov{roll_call_link['href']}"

    bill_link = entry.select_one('div.heading a[href*="congress.gov/bill"]')
    if bill_link:
        vote["bill_number"] = bill_link.text.strip()
        vote["bill_url"] = bill_link.get("href")

    bill_desc = entry.select_one("p.roll-call-description span.billdesc")
    if bill_desc:
        vote["bill_title"] = bill_desc.text.strip()

    for label, key in (("Vote Type:", "vote_type"), ("Status:", "status")):
        value = labelled_value(entry, label)
        if value is not None:
            vote[key] = value

    counts = parse_vote_counts(entry)
    if counts:
        vote["vote_counts"] = counts

    date_div = entry.select_one("div.first-row.row-comment")
    if date_div and date_div.text.strip():
        vote["date"] = date_div.text.strip().split("|")[0].strip()

    return vote


def labelled_value(entry, label):
    """Text that follows a <label>label</label> in the same parent element."""
    label_tag = entry.find("label", string=label)
    if label_tag is None or label_tag.parent is None:
        return None
    return label_tag.parent.text.replace(label, "").strip()


def parse_vote_counts(entry):
    """Tallies from the aria-labels, e.g. 'yea, 215' -> {'yea': 215}."""
    counts = {}
    for tally in entry.select("div.capitalize p[aria-label]"):
        match = re.match(r"\s*([A-Za-z ]+?)\s*,\s*(\d+)", tally["aria-label"])
        if not match:
            continue
        key = COUNT_LABELS.get(match.group(1).strip().lower())
        if key:
            counts[key] = int(match.group(2))
    return counts


# --------------------------------------------------------------------------- #
# Scraper
# --------------------------------------------------------------------------- #

class HouseVotesScraper:
    def __init__(self, congress=119, session=1, proxy=None):
        self.proxy = proxy
        # The public /Votes/ page fills its list from this HTML-fragment
        # endpoint, so we call it directly instead of rendering the page.
        self.list_url = (
            "https://clerk.house.gov/Votes/MemberVotes"
            f"?CongressNum={congress}&Session={ordinal(session)}"
        )
        # Roll-call XML files are organised by calendar year.
        year = congress_first_year(congress) + session - 1
        self.xml_url = f"https://clerk.house.gov/evs/{year}"

    def get_vote_detail(self, roll_call_number):
        """Full record of one roll call, or None if it could not be fetched."""
        xml = fetch(f"{self.xml_url}/roll{int(roll_call_number):03d}.xml", self.proxy)
        return parse_vote_xml(xml) if xml else None

    def scrape_votes(self, limit=50, start_page=1):
        """Collect up to `limit` votes, newest first, walking the paged list."""
        votes = []
        page = start_page
        empty_pages = 0
        while len(votes) < limit:
            if votes:
                time.sleep(PAGE_DELAY)
            html = fetch(f"{self.list_url}&Page={page}", self.proxy, timeout=10)
            page_votes = parse_vote_list_html(html) if html else []

            if not page_votes:
                # A transient failure, or we ran past the last page. Back off and retry.
                empty_pages += 1
                if empty_pages > MAX_EMPTY_PAGES:
                    break
                time.sleep(5 * empty_pages)
                continue

            empty_pages = 0
            votes.extend(page_votes)
            page += 1
        return votes[:limit]


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #

def detail_to_rows(detail):
    """One CSV row per member vote, prefixed with the roll call's key metadata."""
    meta = detail["metadata"]
    context = {
        "congress": meta.get("congress"),
        "session": meta.get("session"),
        "rollcall_num": meta.get("rollcall-num"),
        "legis_num": meta.get("legis-num"),
        "vote_question": meta.get("vote-question"),
        "vote_result": meta.get("vote-result"),
        "action_date": meta.get("action-date"),
    }
    return [{**context, **vote} for vote in detail["votes"]]


def main():
    parser = make_parser("Scrape House roll-call votes from clerk.house.gov")
    parser.add_argument("--rollcall", type=int,
                        help="Roll call number to fetch in full (default: list votes)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Maximum number of votes to list (default: 50)")
    args = parser.parse_args()

    scraper = HouseVotesScraper(args.congress, args.session, args.proxy)
    if args.rollcall:
        detail = scraper.get_vote_detail(args.rollcall)
        if detail is None:
            sys.exit(1)
        output(detail, args.csv, to_rows=detail_to_rows)
    else:
        output(scraper.scrape_votes(args.limit), args.csv)


if __name__ == "__main__":
    main()
