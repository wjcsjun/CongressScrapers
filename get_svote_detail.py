"""Fetch one Senate roll-call vote from senate.gov, including every senator's vote."""
import sys
import xml.etree.ElementTree as ET

from common import fetch, make_parser, output, to_int, xml_children_to_dict

VOTE_URL = (
    "https://www.senate.gov/legislative/LIS/roll_call_votes/"
    "vote{congress}{session}/vote_{congress}_{session}_{vote:05d}.xml"
)
# Child elements with their own structure; everything else is a flat field.
SECTIONS = ("document", "amendment", "count", "tie_breaker", "members")


def parse_vote_xml(xml_string):
    root = ET.fromstring(xml_string)
    vote = xml_children_to_dict(root, skip=SECTIONS)

    for section in ("document", "amendment", "tie_breaker"):
        element = root.find(section)
        if element is not None:
            vote[section] = xml_children_to_dict(element)

    count = root.find("count")
    if count is not None:
        vote["count"] = {
            key: to_int(value, default=value)
            for key, value in xml_children_to_dict(count).items()
        }

    members = root.find("members")
    if members is not None:
        vote["members"] = [xml_children_to_dict(m) for m in members.findall("member")]
    return vote


def get_senate_vote_detail(congress, session, vote_number, proxy=None):
    url = VOTE_URL.format(congress=congress, session=session, vote=int(vote_number))
    xml = fetch(url, proxy)
    return parse_vote_xml(xml) if xml else None


def detail_to_rows(vote):
    """One CSV row per senator, prefixed with the vote's identifying fields."""
    context = {
        key: vote.get(key)
        for key in ("congress", "session", "vote_number", "vote_date",
                    "vote_question_text", "vote_result")
    }
    return [{**context, **member} for member in vote.get("members", [])]


def main():
    parser = make_parser("Fetch one Senate roll-call vote from senate.gov")
    parser.add_argument("-v", "--vote", type=int, required=True, help="Vote number")
    args = parser.parse_args()

    vote = get_senate_vote_detail(args.congress, args.session, args.vote, args.proxy)
    if vote is None:
        sys.exit(1)
    output(vote, args.csv, to_rows=detail_to_rows)


if __name__ == "__main__":
    main()
