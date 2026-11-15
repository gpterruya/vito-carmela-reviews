import json
import logging
import os
import time
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/business.manage"
]

BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / "token.json"
TOKEN_ENV_VAR = "GOOGLE_TOKEN_JSON"

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

# Erros temporários: limite de uso e indisponibilidade do servidor.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
RETRY_BASE_WAIT = 5  # segundos; dobra a cada tentativa (5, 10, 20)
REQUEST_TIMEOUT = 30  # segundos

log = logging.getLogger("vica")


def get_credentials():
    # Na nuvem o token vem da variável de ambiente (segredo do ambiente);
    # no computador, do arquivo token.json.
    token_json = os.environ.get(TOKEN_ENV_VAR)

    if token_json:
        credentials = Credentials.from_authorized_user_info(
            json.loads(token_json),
            SCOPES
        )
    else:
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

        if not token_json:
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
    """GET com novas tentativas para falhas temporárias do Google.

    Só leituras são repetidas; a publicação (PUT) não passa por aqui.
    """

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers=get_headers(),
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
        except (requests.ConnectionError, requests.Timeout) as error:
            if attempt == MAX_ATTEMPTS:
                raise
            reason = f"falha de conexão ({error.__class__.__name__})"
        else:
            if (
                response.status_code not in RETRY_STATUS
                or attempt == MAX_ATTEMPTS
            ):
                response.raise_for_status()
                return response.json()
            reason = f"HTTP {response.status_code}"

        wait = RETRY_BASE_WAIT * 2 ** (attempt - 1)
        log.warning(
            f"Google respondeu com {reason} "
            f"(tentativa {attempt} de {MAX_ATTEMPTS}). "
            f"Nova tentativa em {wait} s."
        )
        time.sleep(wait)


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