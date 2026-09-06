"""Scrape one bill's details and full text from congress.gov.

congress.gov sits behind bot protection that rejects plain HTTP clients, so this
script drives a headless Chrome through Selenium. Chrome must be installed;
webdriver-manager downloads a matching chromedriver automatically.
"""
import re
import sys
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from common import USER_AGENT, log, make_parser, ordinal, output

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
    container = text_page.find("pre", id="billTextContainer")
    return container.text.strip() if container else None


# --------------------------------------------------------------------------- #
# Scraper
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


def main():
    parser = make_parser("Scrape bill details from congress.gov", session=False)
    parser.add_argument("-l", "--legis_num", required=True,
                        help="Legislation number, e.g. HR5, 'S 10' or HJRES25")
    args = parser.parse_args()

    try:
        detail = get_bill_detail(args.congress, args.legis_num, args.proxy)
    except ValueError as error:
        parser.error(str(error))
    output(detail, args.csv)
    if detail["title"] is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
