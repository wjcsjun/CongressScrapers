import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from datetime import datetime
from requests_html import HTMLSession
import re
import time
import pprint
import argparse

import xml.etree.ElementTree as ET


def parse_house_vote_xml(xml_string):
    """
    Parse US House of Representatives vote result XML file and convert to structured JSON format
    """
    # Parse the XML file
    root = ET.fromstring(xml_string)
    
    # Create the basic structure for the output JSON
    vote_json = {
        "metadata": {},
        "party_totals": [],
        "vote_totals": {},
        "votes": []
    }
    
    # Extract vote metadata
    metadata = root.find('vote-metadata')
    if metadata is not None:
        for child in metadata:
            # Skip the vote totals section, will be handled separately
            if child.tag == 'vote-totals':
                continue
            # Add all other metadata elements
            vote_json["metadata"][child.tag] = child.text
    
    # Extract vote totals by party
    vote_totals = metadata.find('vote-totals')
    if vote_totals is not None:
        # Get party totals
        for party_total in vote_totals.findall('totals-by-party'):
            party_data = {}
            for child in party_total:
                party_data[child.tag] = child.text
            vote_json["party_totals"].append(party_data)
        
        # Get overall totals
        overall_totals = vote_totals.find('totals-by-vote')
        if overall_totals is not None:
            for child in overall_totals:
                if child.tag != 'total-stub':  # Skip the label element
                    vote_json["vote_totals"][child.tag] = child.text
    
    # Extract individual vote data
    vote_data = root.find('vote-data')
    if vote_data is not None:
        for recorded_vote in vote_data.findall('recorded-vote'):
            legislator = recorded_vote.find('legislator')
            vote = recorded_vote.find('vote')
            
            if legislator is not None and vote is not None:
                vote_record = {
                    "name": legislator.text,
                    "name_id": legislator.get('name-id'),
                    "party": legislator.get('party'),
                    "state": legislator.get('state'),
                    "role": legislator.get('role'),
                    "vote": vote.text
                }
                vote_json["votes"].append(vote_record)
    
    return vote_json

class HouseVotesScraper:
    def __init__(self, CongressNum: int=119, session: int=1):
        self.congress = CongressNum
        self.year = (CongressNum-118)*2 + 2023 + session-1
        self.session = session

        if str(session) == '1':
            session = '1st'
        elif str(session) == '2':
            session = '2nd'

        self.base_url = f"https://clerk.house.gov/Votes/?{CongressNum=}&Session={session}"
        self.xml_base_url = f'https://clerk.house.gov/evs/{self.year}'
        self.votes = []
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    def get_vote_detail(self, roll_call_number, detail_url=None):
        roll_call_number = str(roll_call_number).zfill(3)
        if detail_url is None:
            detail_url = f"{self.xml_base_url}/roll{roll_call_number}.xml"
        
        print(detail_url)
        response = requests.get(detail_url, headers=self.headers)
        if response.status_code != 200:
            print(f"Error fetching vote detail: {response.status_code}")
            return None
        
        return parse_house_vote_xml(response.text)
        

    
    def scape_votes(self, startPage=1, limit=50):
        all_votes = []
        page = startPage
        
        repeatNum = 0
        while True:            
            url = f"{self.base_url}&Page={page}"
            print(f"Fetching {url} {repeatNum=}...")
            session = HTMLSession()
            r = session.get(url, timeout=10)
            time.sleep(2)
            if not r.ok:
                print(f"Failed to fetch page {page}")
                break

            r.html.render()
            votes = self.parse_votes_html(r.html.html)
            print(len(votes))
            if len(votes) == 0:
                if repeatNum < 5:
                    repeatNum += 1
                    session.close()
                    time.sleep(5*repeatNum)  
                    continue
                else:
                    break
            
            repeatNum = 0

            all_votes.extend(votes)
            if len(all_votes) >= limit:
                break

            page += 1
            session.close()
            time.sleep(5)  # Wait for 5 seconds
        
        self.votes = all_votes
        return all_votes

    @staticmethod
    def parse_votes_html(content):
        """
        Parse vote information from the votes.html file
        Returns a list of dictionaries containing vote details
        """
        
        
        # Use BeautifulSoup to parse HTML
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find all vote entries
        vote_entries = soup.find_all('div', class_='role-call-vote')
        
        votes_data = []
        
        for vote in vote_entries:
            vote_data = {}
            
            # Extract Roll Call Number
            roll_call_link = vote.select_one('div.heading a')
            if roll_call_link:
                vote_data['roll_call_number'] = roll_call_link.text.strip()
                # Extract vote detail link
                vote_id = roll_call_link.get('href')
                if vote_id:
                    vote_data['detail_url'] = f"https://clerk.house.gov{vote_id}"
            
            # Extract Bill Number
            bill_link = vote.select_one('div.heading a[href*="congress.gov/bill"]')
            if bill_link:
                vote_data['bill_number'] = bill_link.text.strip()
                vote_data['bill_url'] = bill_link.get('href')
            
            # Extract Bill Title
            bill_desc = vote.select_one('p.roll-call-description span.billdesc')
            if bill_desc:
                vote_data['bill_title'] = bill_desc.text.strip()
            
            # Extract Vote Type
            vote_type_label = vote.find('label', string='Vote Type:')
            if vote_type_label and vote_type_label.parent:
                vote_data['vote_type'] = vote_type_label.parent.text.replace('Vote Type:', '').strip()
            
            # Extract Status
            status_label = vote.find('label', string='Status:')
            if status_label and status_label.parent:
                vote_data['status'] = status_label.parent.text.replace('Status:', '').strip()
                
            # Extract vote results
            vote_counts = {}
            yea_element = vote.select_one('div.capitalize p[aria-label*="yea"]')
            if yea_element:
                yea_match = re.search(r'yea, (\d+)', yea_element.get('aria-label', ''))
                if yea_match:
                    vote_counts['yea'] = int(yea_match.group(1))
                    
            nay_element = vote.select_one('div.capitalize p[aria-label*="nay"]')
            if nay_element:
                nay_match = re.search(r'nay, (\d+)', nay_element.get('aria-label', ''))
                if nay_match:
                    vote_counts['nay'] = int(nay_match.group(1))
                    
            if vote_counts:
                vote_data['vote_counts'] = vote_counts
            
            # Extract vote date
            date_div = vote.select_one('div.first-row.row-comment')
            if date_div:
                date_text = date_div.text.strip()
                if date_text:
                    vote_data['date'] = date_text.split('|')[0].strip()
                
            votes_data.append(vote_data)
        
        return votes_data

def main():
    parser = argparse.ArgumentParser(description='Scrape House Votes')
    parser.add_argument('-c', '--congress', type=int, default=119, help='Congress number')
    parser.add_argument('-s', '--session', type=int, default=1, help='Session number')
    parser.add_argument('--rollcall', type=int, help='Roll call number to fetch detail')
    parser.add_argument('--limit', type=int, default=50, help='Number of votes to scrape')
    args = parser.parse_args()

    # Instantiate the HouseVotesScraper class
    scraper = HouseVotesScraper(args.congress, args.session)
    
    # Scrape vote information
    if args.rollcall:
        vote_detail = scraper.get_vote_detail(args.rollcall)
        #pprint.pprint(vote_detail['vote_totals'])
        for k,v in vote_detail.items():
            if k == 'votes':
                continue
            pprint.pprint(f"{k}: {v}")
        return
    
    votes = scraper.scape_votes(limit=args.limit)
    pprint.pprint(votes)

if __name__ == "__main__":
    main()
    
    
        