
import json
import os

from cryptography.fernet import Fernet
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.models.gmail_token import GmailToken


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _client_config() -> dict:
    return {
        "web": {
            "client_id": _required_env("GMAIL_CLIENT_ID"),
            "client_secret": _required_env("GMAIL_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_required_env("GMAIL_REDIRECT_URI")],
        }
    }


def _encryption() -> Fernet:
    key = _required_env("GMAIL_TOKEN_ENCRYPTION_KEY")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("GMAIL_TOKEN_ENCRYPTION_KEY is invalid") from exc


def create_oauth_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=GMAIL_SCOPES,
        state=state,
    )
    flow.redirect_uri = _required_env("GMAIL_REDIRECT_URI")
    return flow


def get_authorization_url(state: str) -> str:
    flow = create_oauth_flow(state=state)

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return authorization_url


def complete_oauth(code: str, db: Session) -> str:
    flow = create_oauth_flow()
    flow.fetch_token(code=code)

    credentials = flow.credentials

    if not credentials.refresh_token:
        raise RuntimeError(
            "Google did not return a refresh token. "
            "Please revoke the existing app access in your Google Account "
            "and connect again."
        )

    gmail = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    profile = gmail.users().getProfile(userId="me").execute()
    connected_email = profile.get("emailAddress", "").lower()
    expected_email = _required_env("GMAIL_ACCOUNT").lower()

    if connected_email != expected_email:
        raise RuntimeError(
            f"Connected Google account is {connected_email}, "
            f"but expected {expected_email}."
        )

    encrypted = _encryption().encrypt(
        credentials.to_json().encode("utf-8")
    ).decode("utf-8")

    token_record = (
        db.query(GmailToken)
        .filter(GmailToken.account_email == connected_email)
        .first()
    )

    if token_record:
        token_record.encrypted_credentials = encrypted
    else:
        token_record = GmailToken(
            account_email=connected_email,
            encrypted_credentials=encrypted,
        )
        db.add(token_record)

    db.commit()

    return connected_email


def load_credentials(db: Session):
    from google.oauth2.credentials import Credentials

    account_email = _required_env("GMAIL_ACCOUNT").lower()

    token_record = (
        db.query(GmailToken)
        .filter(GmailToken.account_email == account_email)
        .first()
    )

    if not token_record:
        raise RuntimeError("Gmail is not connected yet. Connect Gmail first.")

    decrypted = _encryption().decrypt(
        token_record.encrypted_credentials.encode("utf-8")
    ).decode("utf-8")

    data = json.loads(decrypted)

    return Credentials.from_authorized_user_info(
        data,
        scopes=GMAIL_SCOPES,
    )
