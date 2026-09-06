# CongressScraper

CongressScraper is a set of small Python command-line scripts for pulling bill
and roll-call vote data from the United States Congress websites
(congress.gov, clerk.house.gov, senate.gov).

Every script prints its result to **stdout as JSON** by default, or as **CSV**
with `--csv`. Progress and error messages go to stderr, so output can be
redirected straight into a file:

```bash
python get_svotes.py -c 119 -s 1 --csv > senate_votes_119_1.csv
```

## Scripts

| Script | Source | What it returns |
|---|---|---|
| `get_bill.py` | congress.gov | One bill: title, sponsor, committees, official and short titles, latest summary, full text |
| `get_house_votes.py` | clerk.house.gov | List of House roll-call votes for a session, or one vote with every member's position |
| `get_svotes.py` | senate.gov | List of Senate roll-call votes for a session |
| `get_svote_detail.py` | senate.gov | One Senate vote: tallies, document/amendment info, every senator's position |

`common.py` holds the code shared by all scripts (HTTP fetching, proxy handling,
XML helpers, argument parsing and JSON/CSV output). It is not run directly.

## Installation

```bash
git clone <your-repository-url>
cd CongressScraper
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

`get_bill.py` without `--govinfo` drives a headless Chrome through Selenium, so
Google Chrome must be installed; `webdriver-manager` downloads a matching
chromedriver on first run. With `--govinfo`, and for all other scripts, only
`requests` and `beautifulsoup4` are used.

## Common options

All scripts accept these options (`-h` shows the full list):

| Option | Meaning |
|---|---|
| `-c`, `--congress` | Congress number (default: 119) |
| `-s`, `--session` | Session number, 1 or 2 (default: 1). Not used by `get_bill.py`. |
| `-p`, `--proxy` | HTTP(S) proxy URL such as `http://host:port`. senate.gov and congress.gov block many non-US IP addresses, so a US exit node is often required. `requests` also honours the `HTTPS_PROXY` environment variable. |
| `--csv` | Print CSV instead of JSON |

## Usage

### Bill details (`get_bill.py`)

```bash
python get_bill.py -c 118 -l HR5 --govinfo
python get_bill.py -c 118 -l "S 10" --govinfo --csv
python get_bill.py -c 118 -l HR5 -p http://proxy-host:port     # scrape congress.gov with Chrome
```

`--govinfo` reads the Government Publishing Office's bulk XML on govinfo.gov
instead of scraping congress.gov. It needs no browser, no API key and no US
proxy, and is the recommended mode. Without it the script drives a headless
Chrome against congress.gov, which blocks most non-US IPs. Both modes return
the same fields; govinfo.gov publishes updates a few hours after congress.gov.

`-l`, `--legis_num` is required and accepts forms such as `HR5`, `hr 5`,
`HJRES25` or `S.J.Res. 25`. Supported types: HR, HRES, HJRES, S, SRES, SJRES.

Fields: `id`, `title`, `sponsor`, `committees`, `official_title`,
`short_titles`, `summary_version` (the bill version the summary describes),
`summary` (plain text, list items as `- ` lines) and `text` (full bill text).
Fields the page does not provide are `null`. If congress.gov blocks the request
the script prints a warning to stderr, outputs nulls and exits with status 1;
in practice a US proxy (`-p`) is needed from outside the United States.

### House votes (`get_house_votes.py`)

```bash
# 50 most recent votes of the 1st session of the 119th Congress
python get_house_votes.py -c 119 -s 1 --limit 50

# Roll call 62 in full, one CSV row per member
python get_house_votes.py -c 119 -s 1 --rollcall 62 --csv
```

* `--limit`: maximum number of votes to list (default: 50). The site serves 10 per page.
* `--rollcall`: fetch this roll call in full instead of listing votes.

### Senate vote list (`get_svotes.py`)

```bash
python get_svotes.py -c 119 -s 1 -p http://proxy-host:port
```

Votes taken *en bloc* (several nominations in one roll call) carry an `en_bloc`
list of the bundled matters instead of a single issue/question/result.

### Senate vote detail (`get_svote_detail.py`)

```bash
python get_svote_detail.py -c 119 -s 1 -v 134 -p http://proxy-host:port --csv
```

* `-v`, `--vote`: the vote number (required).

## CSV layout

* Nested objects are flattened with `_` (for example `vote_counts_yea`).
* Lists (such as `en_bloc` or `short_titles`) are stored as a JSON string in one cell.
* Vote-detail scripts emit one row per member, prefixed with the vote's identifying columns.

## Notes

* Web scraping breaks when the target sites change their markup or feeds.
* Respect the sites' `robots.txt` and terms of service, and keep request rates low.
  The House list scraper pauses between pages.
* `get_bill.py` waits a fixed 8 seconds per page for congress.gov to render.

## License

Distributed under the MIT License.
