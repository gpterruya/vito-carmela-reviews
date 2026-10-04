from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    "https://www.googleapis.com/auth/business.manage"
]

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = BASE_DIR / "credentials" / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"


def authenticate():
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_FILE,
        SCOPES
    )

    credentials = flow.run_local_server(
        port=8080,
        access_type="offline",
        prompt="consent",
    )

    TOKEN_FILE.write_text(
        credentials.to_json(),
        encoding="utf-8"
    )

    print("Autenticação concluída.")
    print(f"Token salvo em: {TOKEN_FILE}")


if __name__ == "__main__":
    authenticate()