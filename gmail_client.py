"""
gmail_client.py - Gmail auth + draft creation.

Reuses the project's credentials.json / token.json, but requests the
gmail.compose scope so it can create DRAFTS (the send-only scope cannot).
If an older send-only token is present it is dropped and you re-authorise
once (a browser window opens).
"""

import base64
import json
from email.mime.text import MIMEText
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def _token_has_scopes():
    try:
        data = json.loads(Path(TOKEN_FILE).read_text(encoding="utf-8"))
        return set(SCOPES).issubset(set(data.get("scopes", [])))
    except Exception:
        return False


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    # An old token from the send-only CLI lacks the drafts scope - drop it so
    # we re-authorise with the right permission.
    if Path(TOKEN_FILE).exists() and not _token_has_scopes():
        Path(TOKEN_FILE).unlink()

    creds = None
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDENTIALS_FILE).exists():
                raise RuntimeError(
                    "Missing credentials.json - see README (Gmail API setup)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def create_draft(service, to_addr, subject, body):
    """Create a Gmail draft and return its id."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to_addr
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return draft.get("id", "")


def send_message(service, to_addr, subject, body):
    """Send an email immediately and return the sent message id.

    Works with the gmail.compose scope (which already covers sending), so no
    extra authorisation is needed beyond what draft creation uses.
    """
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to_addr
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    return sent.get("id", "")
