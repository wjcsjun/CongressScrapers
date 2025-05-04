import xml.etree.ElementTree as ET
import json
import requests
import pprint
import argparse

def parse_senate_votes_xml(xml_string):
    """Parse US Senate vote record XML file and convert to JSON format"""
    try:
        # Parse the XML file
        root = ET.fromstring(xml_string)
        
        # Create the basic data structure
        result = {
            "congress": root.find("congress").text,
            "session": root.find("session").text,
            "congress_year": root.find("congress_year").text,
            "votes": []
        }
        
        # Iterate through all vote records
        for vote_elem in root.find("votes").findall("vote"):
            vote = {
                "vote_number": vote_elem.find("vote_number").text,
                "vote_date": vote_elem.find("vote_date").text,
                "issue": vote_elem.find("issue").text,
                "result": vote_elem.find("result").text,
                "title": vote_elem.find("title").text,
                "vote_tally": {
                    "yeas": int(vote_elem.find("vote_tally/yeas").text),
                    "nays": int(vote_elem.find("vote_tally/nays").text)
                }
            }
            
            # Handle the question element, which may contain nested measure elements
            question_elem = vote_elem.find("question")
            question_text = "".join(question_elem.itertext()).strip()
            vote["question"] = question_text
            
            # Check if there is a measure element
            measure_elem = question_elem.find("measure")
            if measure_elem is not None:
                vote["measure"] = measure_elem.text
            
            result["votes"].append(vote)
        
        return result
    
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return None

def get_senate_votes(congress_num: int=119, session_num: int=1):
    
    # Build the URL
    url = f"https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_{congress_num}_{session_num}.xml"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"Request failed: {response.status_code}")
        return None
    
    # Parse XML and convert to Python dictionary
    votes_data = parse_senate_votes_xml(response.text)
    return votes_data
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape senate Votes')
    parser.add_argument('-c', '--congress', type=int, default=119, help='Congress number')
    parser.add_argument('-s', '--session', type=int, default=1, help='Session number')
    args = parser.parse_args()

    votes = get_senate_votes(args.congress, args.session)
    pprint.pprint(votes)
    