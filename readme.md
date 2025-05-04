# CongressScraper

CongressScraper is a Python project for scraping bill and vote data from United States Congress websites (congress.gov, house.gov, senate.gov).

## Features

This project includes the following scripts:

*   `get_bill.py`: Scrapes detailed information for a specified bill from congress.gov, including sponsor, committees, official title, short titles, summary, and the full text of the bill.
*   `get_house_votes.py`: Scrapes the list of votes from the House of Representatives (clerk.house.gov) and optionally fetches detailed information for a specific roll call vote (including how each member voted).
*   `get_svotes.py`: Scrapes the list of Senate votes for a specified session from senate.gov.
*   `get_svote_detail.py`: Scrapes detailed information for a specified Senate vote from senate.gov, including vote tallies and how each senator voted.

## Installation

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone <your-repository-url>
    cd CongressScraper
    ```

2.  **Create and activate a virtual environment** (recommended):
    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    Note: The `get_bill.py` script uses Selenium and `webdriver-manager` to drive a web browser (Chrome). `webdriver-manager` will automatically download and manage the required ChromeDriver.

## Usage

All scripts support command-line arguments to specify the Congress number, session, and other relevant details. You can use the `-h` or `--help` argument to see the detailed options for each script.

### Get Bill Details (`get_bill.py`)

```bash
python get_bill.py -c <congress_number> -l <legislation_number>
```

*   `-c`, `--congress`: The Congress number (e.g., 118).
*   `-l`, `--legis_num`: The legislation number (e.g., 'HR5' or 'S10'). **Required**.

**Example:** Get details for bill HR5 from the 118th Congress
```bash
python get_bill.py -c 118 -l HR5
```

### Get House Votes (`get_house_votes.py`)

**Get vote list:**
```bash
python get_house_votes.py -c <congress_number> -s <session_number> [--limit <number>]
```
*   `-c`, `--congress`: The Congress number (default: 119).
*   `-s`, `--session`: The session number (default: 1).
*   `--limit`: The maximum number of votes to scrape (default: 50).

**Example:** Get the 50 most recent votes for the 1st session of the 119th Congress
```bash
python get_house_votes.py -c 119 -s 1 --limit 50
```

**Get specific vote details:**
```bash
python get_house_votes.py -c <congress_number> -s <session_number> --rollcall <rollcall_number>
```
*   `--rollcall`: The roll call number for which to fetch details.

**Example:** Get details for roll call vote 62 from the 1st session of the 119th Congress
```bash
python get_house_votes.py -c 119 -s 1 --rollcall 62
```

### Get Senate Vote List (`get_svotes.py`)

```bash
python get_svotes.py -c <congress_number> -s <session_number>
```
*   `-c`, `--congress`: The Congress number (default: 119).
*   `-s`, `--session`: The session number (default: 1).

**Example:** Get the Senate vote list for the 1st session of the 119th Congress
```bash
python get_svotes.py -c 119 -s 1
```

### Get Senate Vote Detail (`get_svote_detail.py`)

```bash
python get_svote_detail.py -c <congress_number> -s <session_number> -v <vote_number>
```
*   `-c`, `--congress`: The Congress number (default: 119).
*   `-s`, `--session`: The session number (default: 1).
*   `-v`, `--vote`: The vote number (default: 134).

**Example:** Get details for Senate vote 134 from the 1st session of the 119th Congress
```bash
python get_svote_detail.py -c 119 -s 1 -v 134
```

## Notes

*   Web scraping can break if the structure of the target websites changes.
*   Please respect the `robots.txt` files and terms of service of the target websites.
*   Making frequent requests might get your IP address blocked. It's recommended to add appropriate delays between requests (some scripts already include delays).
*   `get_bill.py` depends on Selenium and Chrome/ChromeDriver. Ensure your environment is set up correctly.

## License
Distributed under the MIT License.