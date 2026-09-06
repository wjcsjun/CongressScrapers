"""Fetch one bill's details and full text.

Two data sources produce the same set of fields:

* Default: scrape congress.gov. The site sits behind bot protection that
  rejects plain HTTP clients, so this mode drives a headless Chrome through
  Selenium (Chrome must be installed; webdriver-manager fetches chromedriver).
* --govinfo: read the Government Publishing Office's bulk XML (BILLSTATUS and
  bill text) from govinfo.gov with plain HTTP requests. No browser, no API key.
"""
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from common import USER_AGENT, fetch, log, make_parser, ordinal, output, xml_text

SITE = "https://www.congress.gov"
PAGE_LOAD_WAIT = 8  # seconds; congress.gov renders much of the page client-side

BILL_TYPES = {
    "HR": "house-bill",
    "HRES": "house-resolution",
    "HJRES": "house-joint-resolution",
    "S": "senate-bill",
    "SRES": "senate-resolution",
    "SJRES": "senate-joint-resolution",
}

# How congress.gov displays each bill type, e.g. "H.R.5", "S.J.Res.25".
DISPLAY_PREFIX = {
    "HR": "H.R.", "HRES": "H.Res.", "HJRES": "H.J.Res.",
    "S": "S.", "SRES": "S.Res.", "SJRES": "S.J.Res.",
}

GOVINFO_STATUS_URL = (
    "https://www.govinfo.gov/bulkdata/BILLSTATUS/{congress}/{type}/"
    "BILLSTATUS-{congress}{type}{number}.xml"
)
GOVINFO_TEXT_URL = "https://www.govinfo.gov/content/pkg/{package}/html/{package}.htm"

# The all-info page's <h1> reads e.g.
# "All Information (Except Text) for H.R.5 - Parents Bill of Rights Act
#  118th Congress (2023-2024)"; keep just the bill number and name.
TITLE_PREFIX = re.compile(r"^All Information \(Except Text\) for\s+")
TITLE_SUFFIX = re.compile(r"\s+\d+(?:st|nd|rd|th) Congress \(\d{4}-\d{4}\)$")


def split_bill_number(legis_num):
    """'HR5', 'hr 5' or 'H.J.Res. 25' -> ('HR', '5') / ('HJRES', '25')."""
    compact = re.sub(r"[\s.]", "", legis_num).upper()
    match = re.fullmatch(r"([A-Z]+)(\d+)", compact)
    if not match or match.group(1) not in BILL_TYPES:
        raise ValueError(f"Unsupported legislation number: {legis_num!r}")
    return match.group(1), match.group(2)


# --------------------------------------------------------------------------- #
# Browser
# --------------------------------------------------------------------------- #

def make_driver(proxy=None):
    options = Options()
    for argument in ("--headless", "--no-sandbox", "--disable-dev-shm-usage",
                     f"user-agent={USER_AGENT}"):
        options.add_argument(argument)
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def load_page(driver, url):
    """Open url, wait for client-side rendering, and return the parsed page."""
    log(f"Loading {url}")
    driver.get(url)
    time.sleep(PAGE_LOAD_WAIT)
    return BeautifulSoup(driver.page_source, "html.parser")


# --------------------------------------------------------------------------- #
# Page parsing
# --------------------------------------------------------------------------- #

def parse_bill_info(soup):
    """Title, sponsor, committees, titles and summary from the all-info page."""
    overview = soup.find("div", class_="overview_wrapper") or soup
    return {
        "title": bill_title(soup),
        "sponsor": overview_field(overview, "Sponsor:"),
        "committees": overview_field(overview, "Committees:"),
        "official_title": official_title(soup),
        "short_titles": short_titles(soup),
        **latest_summary(soup),
    }


def bill_title(soup):
    heading = soup.find("h1", class_="legDetail")
    if not heading:
        return None
    text = " ".join(heading.text.split())
    return TITLE_SUFFIX.sub("", TITLE_PREFIX.sub("", text))


def overview_field(overview, label):
    """Value cell of the overview-table row whose header is `label`."""
    header = overview.find("th", attrs={"scope": "row"}, string=label)
    cell = header.find_next_sibling("td") if header else None
    return cell.text.strip() if cell else None


def official_title(soup):
    heading = soup.find(string=re.compile("Official Title as Introduced"))
    paragraph = heading.parent.find_next("p") if heading else None
    return " ".join(paragraph.text.split()) if paragraph else None


def short_titles(soup):
    """Distinct short titles in page order.

    The titles section holds both "Short Titles" and "Official Titles"
    sub-sections, each introduced by an <h3>; only paragraphs under the former
    are short titles.
    """
    section = soup.find("div", id="titles_main")
    if not section:
        return []
    titles = []
    in_short_titles = False
    for tag in section.find_all(["h3", "p"]):
        if tag.name == "h3":
            in_short_titles = tag.text.strip().startswith("Short Title")
        elif in_short_titles:
            titles.extend(line.strip() for line in tag.text.splitlines() if line.strip())
    return list(dict.fromkeys(titles))


def latest_summary(soup):
    """The latest CRS summary as plain text, plus the bill version it describes.

    The summary block is a heading (<h3 class="currentVersion">) followed by
    sibling <p>/<ul> elements up to an <hr>.
    """
    container = soup.find("div", id="latestSummary-content")
    heading = container.find(class_="currentVersion") if container else None
    if heading is None:
        return {"summary_version": None, "summary": None}

    version = heading.find("span")
    blocks = []
    for sibling in heading.find_next_siblings():
        if sibling.name == "hr":
            break
        blocks.append(block_text(sibling))
    return {
        "summary_version": " ".join(version.text.split()) if version else None,
        "summary": "\n\n".join(block for block in blocks if block) or None,
    }


def block_text(tag):
    """Whitespace-normalised text of a block; list items become '- item' lines."""
    if tag.name in ("ul", "ol"):
        return "\n".join("- " + " ".join(li.text.split()) for li in tag.find_all("li"))
    return " ".join(tag.text.split())


def plain_text_url(text_page):
    """Link to the plain-text version of the bill, from the text-format selector."""
    selector = text_page.find("div", class_="cdg-summary-wrapper", id="textSelector")
    for link in selector.find_all("a") if selector else []:
        if "format=txt" in (link.get("href") or ""):
            return SITE + link["href"]
    return None


def bill_text(text_page):
    """Plain bill text: congress.gov wraps it in <pre id="billTextContainer">,
    govinfo.gov in a bare <pre>."""
    container = text_page.find("pre", id="billTextContainer") or text_page.find("pre")
    return container.text.strip() if container else None


# --------------------------------------------------------------------------- #
# Source 1: congress.gov via headless Chrome
# --------------------------------------------------------------------------- #

def get_bill_detail(congress, legis_num, proxy=None):
    bill_type, number = split_bill_number(legis_num)
    bill_url = f"{SITE}/bill/{ordinal(congress)}-congress/{BILL_TYPES[bill_type]}/{number}"
    detail = {"id": f"{congress}-{bill_type}{number}"}

    driver = make_driver(proxy)
    try:
        info_page = load_page(driver, f"{bill_url}/all-info")
        detail.update(parse_bill_info(info_page))
        if detail["title"] is None:
            page_title = info_page.title.text.strip() if info_page.title else "no <title>"
            log(f"Warning: bill page did not render as expected (page title: {page_title!r}). "
                "congress.gov may have blocked the request; try --proxy with a US exit node.")
        text_url = plain_text_url(load_page(driver, f"{bill_url}/text"))
        detail["text"] = bill_text(load_page(driver, text_url)) if text_url else None
    finally:
        driver.quit()
    return detail


# --------------------------------------------------------------------------- #
# Source 2: govinfo.gov bulk XML (no browser)
# --------------------------------------------------------------------------- #

def get_bill_detail_govinfo(congress, legis_num, proxy=None):
    """Same fields as get_bill_detail, built from GPO's BILLSTATUS XML."""
    bill_type, number = split_bill_number(legis_num)
    type_code = bill_type.lower()
    status_xml = fetch(
        GOVINFO_STATUS_URL.format(congress=congress, type=type_code, number=number), proxy
    )
    if status_xml is None:
        log("GovInfo has no status file for this bill (it may not exist, or is not published yet).")
        return None
    bill = ET.fromstring(status_xml).find("bill")

    detail = {"id": f"{congress}-{bill_type}{number}"}
    detail.update(parse_bill_status(bill, bill_type, number))

    detail["text"] = None
    package = latest_text_package(bill)
    if package:
        text_html = fetch(GOVINFO_TEXT_URL.format(package=package), proxy)
        if text_html:
            detail["text"] = bill_text(BeautifulSoup(text_html, "html.parser"))
    return detail


def parse_bill_status(bill, bill_type, number):
    """Title, sponsor, committees, titles and summary, formatted like congress.gov."""
    titles = [(xml_text(item, "titleType") or "", xml_text(item, "title") or "")
              for item in bill.findall("titles/item")]
    committees = [
        f"{xml_text(item, 'chamber')} - {xml_text(item, 'name')}"
        for item in bill.findall("committees/item")
    ]
    official = [title for kind, title in titles if kind.startswith("Official Title as Introduced")]
    short = [title for kind, title in titles if kind.startswith("Short Title")]
    return {
        "title": f"{DISPLAY_PREFIX[bill_type]}{number} - {xml_text(bill, 'title')}",
        "sponsor": sponsor_line(bill),
        "committees": " | ".join(committees) or None,
        "official_title": official[0] if official else None,
        "short_titles": list(dict.fromkeys(short)),
        **govinfo_summary(bill),
    }


def sponsor_line(bill):
    """'Rep. Letlow, Julia [R-LA-5] (Introduced 03/01/2023)', as congress.gov shows it."""
    sponsor = bill.find("sponsors/item")
    if sponsor is None:
        return None
    introduced = us_date(xml_text(bill, "introducedDate"))
    name = xml_text(sponsor, "fullName")
    return f"{name} (Introduced {introduced})" if introduced else name


def govinfo_summary(bill):
    """Most recent CRS summary as plain text, plus the version it describes."""
    summaries = bill.findall("summaries/summary")
    if not summaries:
        return {"summary_version": None, "summary": None}
    latest = max(summaries, key=lambda item: xml_text(item, "actionDate") or "")
    # The summary body is HTML, stored under <text> or <cdata><text>.
    body = xml_text(latest, "text") or xml_text(latest, "cdata/text") or ""
    blocks = [block_text(tag) for tag in BeautifulSoup(body, "html.parser").find_all(recursive=False)]
    return {
        "summary_version": f"{xml_text(latest, 'actionDesc')} ({us_date(xml_text(latest, 'actionDate'))})",
        "summary": "\n\n".join(block for block in blocks if block) or None,
    }


def latest_text_package(bill):
    """GovInfo package id (e.g. 'BILLS-118hr5rfs') of the newest text version."""
    versions = [item for item in bill.findall("textVersions/item") if xml_text(item, "date")]
    if not versions:
        return None
    newest = max(versions, key=lambda item: xml_text(item, "date"))
    url = xml_text(newest, "formats/item/url") or ""
    match = re.search(r"/pkg/([^/]+)/", url)
    return match.group(1) if match else None


def us_date(iso_date):
    """'2023-03-01' -> '03/01/2023'; None stays None."""
    if not iso_date:
        return None
    return datetime.strptime(iso_date[:10], "%Y-%m-%d").strftime("%m/%d/%Y")


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #

def main():
    parser = make_parser("Fetch bill details from congress.gov (Chrome) or govinfo.gov (--govinfo)", session=False)
    parser.add_argument("-l", "--legis_num", required=True,
                        help="Legislation number, e.g. HR5, 'S 10' or HJRES25")
    parser.add_argument("--govinfo", action="store_true",
                        help="Read GovInfo bulk XML instead of scraping congress.gov "
                             "with Chrome (no browser or US proxy needed)")
    args = parser.parse_args()

    fetch_detail = get_bill_detail_govinfo if args.govinfo else get_bill_detail
    try:
        detail = fetch_detail(args.congress, args.legis_num, args.proxy)
    except ValueError as error:
        parser.error(str(error))
    if detail is None:
        sys.exit(1)
    output(detail, args.csv)
    if detail["title"] is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
