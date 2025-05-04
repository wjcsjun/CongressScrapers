import xml.etree.ElementTree as ET
import json
import argparse
import requests

def parse_vote_xml(xml_file):
    """
    Parse XML file containing Senate vote details and convert to a JSON-compatible dictionary
    """
    try:
        # Parse XML file
        #tree = ET.parse(xml_file)
        #root = tree.getroot()
        root = ET.fromstring(xml_file)
        
        # Create a dictionary to store all vote data
        vote_data = {}
        
        # Extract basic vote information
        for child in root:
            if child.tag not in ('members', 'document', 'amendment', 'count', 'tie_breaker'):
                vote_data[child.tag] = child.text
        
        # Extract document information
        document = root.find('document')
        if document is not None:
            vote_data['document'] = {}
            for child in document:
                vote_data['document'][child.tag] = child.text
        
        # Extract amendment information
        amendment = root.find('amendment')
        if amendment is not None:
            vote_data['amendment'] = {}
            for child in amendment:
                vote_data['amendment'][child.tag] = child.text
        
        # Extract vote counts
        count = root.find('count')
        if count is not None:
            vote_data['count'] = {}
            for child in count:
                # Convert numeric values to integers
                if child.text and child.text.isdigit():
                    vote_data['count'][child.tag] = int(child.text)
                else:
                    vote_data['count'][child.tag] = child.text
        
        # Extract tie-breaker information (if any)
        tie_breaker = root.find('tie_breaker')
        if tie_breaker is not None:
            vote_data['tie_breaker'] = {}
            for child in tie_breaker:
                vote_data['tie_breaker'][child.tag] = child.text
        
        # Extract member votes
        members = root.find('members')
        if members is not None:
            vote_data['members'] = []
            for member in members.findall('member'):
                member_data = {}
                for child in member:
                    member_data[child.tag] = child.text
                vote_data['members'].append(member_data)
        
        return vote_data
    
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return None

def get_senate_vote_detail(congress, session, vote_num):

    base_url = "https://www.senate.gov/legislative/LIS/roll_call_votes/"

    xml_url = f"{base_url}vote{congress}{session}/vote_{args.congress}_{args.session}_{vote_num}.xml"
    print(xml_url)

    response = requests.get(xml_url)
    if response.status_code != 200:
        print(f"请求失败: {response.status_code}")
        return None

    
    # Parse the XML file and convert to JSON
    vote_data = parse_vote_xml(response.text)

    return vote_data
    
    

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Get Senate Vote Details')
    parser.add_argument('-c', '--congress', type=int, default=119, help='Congress number')
    parser.add_argument('-s', '--session', type=int, default=1, help='Session number')
    parser.add_argument('-v', '--vote', type=int, default=134, help='Vote number')
    args = parser.parse_args()  

    vote_num = str(args.vote).zfill(5)

    vote_data = get_senate_vote_detail(args.congress, args.session, vote_num)

    if vote_data:
        # Print summary information
        print("\nVote Summary:")
        print(f"Congress: {vote_data.get('congress', 'N/A')}")
        print(f"Vote Number: {vote_data.get('vote_number', 'N/A')}")
        print(f"Date: {vote_data.get('vote_date', 'N/A')}")
        print(f"Question: {vote_data.get('vote_question_text', 'N/A')}")
        print(f"Result: {vote_data.get('vote_result', 'N/A')}")
        
        if 'count' in vote_data:
            print("\nVote Statistics:")
            for key, value in vote_data['count'].items():
                print(f"  {key.capitalize()}: {value}")
                
        print("\nJSON Output Example (partial):")
        print(json.dumps({k: vote_data[k] for k in list(vote_data.keys())[:15]}, indent=2))
        print("...")
    else:
        print("Failed to parse XML file")