from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/business.manage"
]

BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / "token.json"

ACCOUNT_ID = "109953788990608851050"
LOCATION_ID = "6193849696396283535"

ACCOUNT_MANAGEMENT_API = (
    "https://mybusinessaccountmanagement.googleapis.com/v1"
)

BUSINESS_INFORMATION_API = (
    "https://mybusinessbusinessinformation.googleapis.com/v1"
)

REVIEWS_API = (
    "https://mybusiness.googleapis.com/v4"
)


def get_credentials():
    credentials = Credentials.from_authorized_user_file(
        TOKEN_FILE,
        SCOPES
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8"
        )

    return credentials


def get_headers():
    credentials = get_credentials()

    return {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }


def get(url, params=None):
    response = requests.get(
        url,
        headers=get_headers(),
        params=params,
    )

    response.raise_for_status()

    return response.json()


def get_accounts():
    url = f"{ACCOUNT_MANAGEMENT_API}/accounts"

    return get(url)


def get_locations():
    url = (
        f"{BUSINESS_INFORMATION_API}"
        f"/accounts/{ACCOUNT_ID}/locations"
    )

    params = {
        "readMask": "name,title,websiteUri"
    }

    return get(url, params)


if __name__ == "__main__":
    print(get_accounts())
    print(get_locations())