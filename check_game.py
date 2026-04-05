import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

DODGERS_TEAM_ID = 119
DODGER_STADIUM_VENUE_ID = 22
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
PT = ZoneInfo("America/Los_Angeles")


def get_today_pt() -> str:
    raw = os.environ.get("GAME_DATE")
    if raw:
        return raw
    return datetime.now(PT).strftime("%Y-%m-%d")


def fetch_schedule(date: str) -> dict:
    url = f"{MLB_SCHEDULE_URL}?sportId=1&teamId={DODGERS_TEAM_ID}&date={date}&hydrate=team,venue"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def find_home_games(data: dict) -> list[dict]:
    if not data.get("dates"):
        return []

    home_games = []
    for game in data["dates"][0]["games"]:
        if game.get("status", {}).get("detailedState") == "Postponed":
            continue
        is_home = game["teams"]["home"]["team"]["id"] == DODGERS_TEAM_ID
        at_dodger_stadium = game.get("venue", {}).get("id") == DODGER_STADIUM_VENUE_ID
        if is_home and at_dodger_stadium:
            home_games.append(game)
    return home_games


def format_message(game: dict) -> str:
    opponent = game["teams"]["away"]["team"]["name"]
    game_time_utc = datetime.fromisoformat(game["gameDate"].replace("Z", "+00:00"))
    game_time_pt = game_time_utc.astimezone(PT)
    start_time = game_time_pt.strftime("%-I:%M %p PT")
    venue = game.get("venue", {}).get("name", "Dodger Stadium")
    return (
        f"Dodgers home game today!\n"
        f"vs. {opponent}\n"
        f"First pitch: {start_time}\n"
        f"{venue}"
    )


def send_sms(body: str, gmail_address: str, app_password: str, sms_address: str) -> None:
    msg = MIMEText(body)
    msg["From"] = gmail_address
    msg["To"] = sms_address
    msg["Subject"] = ""
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, sms_address, msg.as_string())


def main() -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    sms_address = os.environ.get("SMS_ADDRESS")

    if not all([gmail_address, app_password, sms_address]):
        print("Error: GMAIL_ADDRESS, GMAIL_APP_PASSWORD, and SMS_ADDRESS must be set.", file=sys.stderr)
        sys.exit(1)

    date = get_today_pt()
    print(f"Checking MLB schedule for {date}...")

    try:
        data = fetch_schedule(date)
    except Exception as e:
        print(f"Error fetching MLB schedule: {e}", file=sys.stderr)
        sys.exit(1)

    home_games = find_home_games(data)

    if not home_games:
        print("No Dodgers home game today.")
        return

    for game in home_games:
        message = format_message(game)
        print(f"Home game found! Sending SMS:\n{message}")
        send_sms(message, gmail_address, app_password, sms_address)
        print("SMS sent.")


if __name__ == "__main__":
    main()
