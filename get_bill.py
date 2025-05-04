from bs4 import BeautifulSoup

from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import re
import pprint
import argparse


def split_bill_number(bill_id):
    """
    Split the bill number into prefix and numeric parts.
    
    Args:
        bill_id (str): The bill number, e.g., 'hr198', 'hrs1988', 'hjres25', etc.
        
    Returns:
        list: A list containing two elements [prefix, number].
    """
    # Use regular expression to match the letter part and the number part
    match = re.match(r'([a-zA-Z]+)(\d+)', bill_id.upper())
    
    if match:
        prefix = match.group(1)  # Letter part
        number = match.group(2)  # Number part
        return [prefix, number]
    else:
        # If the format does not match, return the original string and an empty string
        return [bill_id, '']

bill_type_map: dict = {
    'HR': 'house-bill',
    'HRES': 'house-resolution',
    'HJRES': 'house-joint-resolution',
    'S': 'senate-bill',
    'SRES': 'senate-resolution',
    'SJRES': 'senate-joint-resolution'
}

def get_next_non_empty_sibling(tag):
    next_sib = tag.next_sibling
    while next_sib and not next_sib.text.strip():
        #print(next_sib, "in line 117")
        next_sib = next_sib.next_sibling
    return next_sib

def get_bill_detail(congress: int, legis_num: str):
    """
    Get bill details.
    """
    base_url = 'https://www.congress.gov/bill'
    legis_num = legis_num.upper()
    bill_detail = {}
    bill_detail['id'] = f'{congress}-{''.join(legis_num.split())}'
    congress = f'{congress}th-congress'
    if ' ' in legis_num:
        legnumlist = legis_num.split()
    else:
        legnumlist = split_bill_number(legis_num)
    

    bill_num = legnumlist[-1]
    bill_type = ''.join(legnumlist[:-1])
    bill_type = bill_type_map.get(bill_type, 'unknown')
    if bill_type == 'unknown':
        raise ValueError(f"Unsupported bill type: {bill_type}")
    
    bill_url = f'{base_url}/{congress}/{bill_type}/{bill_num}/all-info'
    texturl = f'{base_url}/{congress}/{bill_type}/{bill_num}/text'
    print(bill_url)
    print(texturl)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={headers['User-Agent']}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.get(bill_url)
    time.sleep(8)  # Wait for the page to load

    html = driver.page_source
    
    soup = BeautifulSoup(html, 'html.parser')

    
            
    # Extract Bill Title
    title_element = soup.find('h1', class_='legDetail')
    if title_element:
        bill_detail['title'] = title_element.text.strip()
    

    overview_wrapper = soup.find('div', class_='overview_wrapper')

    # Extract Sponsor
    sponsor_element = overview_wrapper.find('th', attrs={'scope': 'row'}, string='Sponsor:')
    
    if sponsor_element:
        sponsor = sponsor_element.find_next_sibling('td')
        if sponsor:
            bill_detail['sponsor'] = sponsor.text.strip()
    
    # Extract committees
    committees_element = overview_wrapper.find('th', attrs={'scope': 'row'}, string='Committees:')
    if committees_element:
        committees = committees_element.find_next_sibling('td')
        if committees:
            bill_detail['committees'] = committees.text.strip()
    
    title_section = soup.find(string=re.compile('Official Title as Introduced'))
    
    if title_section:
        #print(title_section.parent)
        #print(title_section.parent.parent.find("p"))
        official_title = title_section.parent.parent.find("p").text.strip()
    
    bill_detail['official_title'] = official_title

    #<div id="titles_main">
    short_titles_section = soup.find('div', id='titles_main')
    #print(short_titles_section)
    if short_titles_section:
        short_titles = [short_title.text.strip() for short_title in short_titles_section.find_all('p')]
    

    newshort_titles = []
    for short in short_titles[:-1]:
        newshort_titles.extend(short.splitlines())
    
    for sk in range(len(newshort_titles)):
        newshort_titles[sk] = newshort_titles[sk].strip()
    
    newshort_titles = list(set(newshort_titles))
    
    
    bill_detail['short_titles'] = newshort_titles
    

    bill_detail['summary'] = ''

    latest_summary = soup.find('div', id='latestSummary-content')
    #print(latest_summary)
    if latest_summary:
        current_summary = latest_summary.find(class_="currentVersion")
        #print(current_summary)
        if current_summary:
            #print(get_next_non_empty_sibling(current_summary))
            if get_next_non_empty_sibling(current_summary):
                bill_detail['summary'] = get_next_non_empty_sibling(current_summary).text.strip()
    
    # Extract text
    driver.get(texturl)
    time.sleep(8)  # Wait for the page to load
    text_html = driver.page_source
    text_soup = BeautifulSoup(text_html, 'html.parser')
    text_section = text_soup.find('div', class_='cdg-summary-wrapper', id='textSelector')
    if text_section:
        atags = text_section.find_all('a')
        for atag in atags:
            if 'format=txt' in atag.get('href'):
                txturl = atag.get('href')
                break
    
    print(txturl)
    txturl = 'https://www.congress.gov'+txturl
    
    driver.get(txturl)
    time.sleep(8)  # Wait for the page to load
    text_html = driver.page_source
    
    bill_detail['text'] = ''
    text_soup = BeautifulSoup(text_html, 'html.parser')
    text_section = text_soup.find('pre', id='billTextContainer')  ##billTextContainer
    if text_section:
        bill_detail['text'] = text_section.text.strip()

    driver.quit()
    return bill_detail

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape bill details')
    parser.add_argument('-c', '--congress', type=int, default=119, help='Congress number')
    parser.add_argument('-l', '--legis_num', type=str, help='Legislation number')
    args = parser.parse_args()
    detail = get_bill_detail(args.congress, args.legis_num)
    pprint.pprint(detail)




    