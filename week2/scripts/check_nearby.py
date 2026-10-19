"""Diagnose public ZIP/place lookup without AI or real group data (host GEOAPIFY_API_KEY required)."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
from referee.nearby import find_places
from referee.providers import ProviderError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip',help='Five-digit US ZIP, for example 75201')
    args=parser.parse_args()
    try:
        result=find_places(args.zip)
        print(json.dumps({'zip':result['zip'],'area':result['area'],'place_count':len(result['places'])},indent=2))
        return 0
    except (ProviderError,ValueError) as error:
        print(str(error),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
