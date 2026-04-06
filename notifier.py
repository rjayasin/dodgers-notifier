import json
import os
import smtplib
import sys
import urllib.request
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

DODGERS_TEAM_ID = 119
DODGER_STADIUM_VENUE_ID = 22
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
PT = ZoneInfo("America/Los_Angeles")


def fetch_schedule(**params: str) -> dict:
    base_params = f"sportId=1&teamId={DODGERS_TEAM_ID}&hydrate=team,venue"
    extra = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{MLB_SCHEDULE_URL}?{base_params}&{extra}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def send_sms(body: str, gmail_address: str, app_password: str, sms_address: str) -> None:
    msg = MIMEText(body)
    msg["From"] = gmail_address
    msg["To"] = sms_address
    msg["Subject"] = ""
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, sms_address, msg.as_string())


def load_config() -> tuple[str, str, str]:
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    sms_address = os.environ.get("SMS_ADDRESS")

    if not all([gmail_address, app_password, sms_address]):
        print("Error: GMAIL_ADDRESS, GMAIL_APP_PASSWORD, and SMS_ADDRESS must be set.", file=sys.stderr)
        sys.exit(1)

    return gmail_address, app_password, sms_address
