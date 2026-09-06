"""List the roll-call votes of one Senate session from senate.gov's XML feed."""
import sys
import xml.etree.ElementTree as ET

from common import fetch, make_parser, output, to_int, xml_text

VOTE_MENU_URL = "https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_{congress}_{session}.xml"


def parse_vote(vote_elem):
    vote = {
        "vote_number": xml_text(vote_elem, "vote_number"),
        "vote_date": xml_text(vote_elem, "vote_date"),
        "issue": xml_text(vote_elem, "issue"),
        "question": None,
        "result": xml_text(vote_elem, "result"),
        "title": xml_text(vote_elem, "title"),
        "vote_tally": {
            "yeas": to_int(xml_text(vote_elem, "vote_tally/yeas")),
            "nays": to_int(xml_text(vote_elem, "vote_tally/nays")),
        },
    }

    # <question> may wrap a <measure> element; itertext() joins both texts and
    # split/join collapses the XML indentation between them into single spaces.
    question = vote_elem.find("question")
    if question is not None:
        vote["question"] = " ".join("".join(question.itertext()).split())
        measure = question.find("measure")
        if measure is not None:
            vote["measure"] = measure.text

    # En bloc votes bundle several matters (e.g. nominations) into one roll
    # call; their issue/question/result live under <en_bloc><matter>.
    en_bloc = vote_elem.find("en_bloc")
    if en_bloc is not None:
        vote["en_bloc"] = [
            {
                "issue": xml_text(matter, "issue"),
                "question": xml_text(matter, "question"),
                "result": xml_text(matter, "result"),
            }
            for matter in en_bloc.findall("matter")
        ]
    return vote


def parse_senate_votes_xml(xml_string):
    root = ET.fromstring(xml_string)
    return {
        "congress": xml_text(root, "congress"),
        "session": xml_text(root, "session"),
        "congress_year": xml_text(root, "congress_year"),
        "votes": [parse_vote(vote) for vote in root.find("votes").findall("vote")],
    }


def get_senate_votes(congress=119, session=1, proxy=None):
    xml = fetch(VOTE_MENU_URL.format(congress=congress, session=session), proxy)
    return parse_senate_votes_xml(xml) if xml else None


def main():
    parser = make_parser("List Senate roll-call votes from senate.gov")
    args = parser.parse_args()

    votes = get_senate_votes(args.congress, args.session, args.proxy)
    if votes is None:
        sys.exit(1)
    output(votes, args.csv, to_rows=lambda data: data["votes"])


if __name__ == "__main__":
    main()
