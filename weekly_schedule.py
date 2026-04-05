import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

DODGERS_TEAM_ID = 119
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
PT = ZoneInfo("America/Los_Angeles")


def get_week_range() -> tuple[str, str]:
    """Return (start, end) as YYYY-MM-DD strings for Mon–Sun of the coming week."""
    today = datetime.now(PT).date()
    # days_until_monday: if today is Sunday (weekday=6), next Monday is tomorrow
    days_until_monday = (7 - today.weekday()) % 7 or 7
    monday = today + timedelta(days=days_until_monday)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def fetch_schedule(start_date: str, end_date: str) -> dict:
    url = (
        f"{MLB_SCHEDULE_URL}?sportId=1&teamId={DODGERS_TEAM_ID}"
        f"&startDate={start_date}&endDate={end_date}&hydrate=team,venue"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def parse_home_games(data: dict) -> list[dict]:
    games = []
    for date_entry in data.get("dates", []):
        for game in date_entry["games"]:
            if game.get("status", {}).get("detailedState") == "Postponed":
                continue
            if game["teams"]["home"]["team"]["id"] == DODGERS_TEAM_ID:
                games.append(game)
    return games


def format_game_line(game: dict) -> str:
    opponent = game["teams"]["away"]["team"]["name"]

    game_time_utc = datetime.fromisoformat(game["gameDate"].replace("Z", "+00:00"))
    game_time_pt = game_time_utc.astimezone(PT)
    day = game_time_pt.strftime("%a %-m/%-d")
    start_time = game_time_pt.strftime("%-I:%M %p PT")

    return f"{day}  🆚 {opponent}  ⏰ {start_time}"


def format_message(start_date: str, end_date: str, games: list[dict]) -> str:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    header = f"⚾ Dodgers schedule ({start.strftime('%b %-d')}–{end.strftime('%-d')})\n"

    if not games:
        return header + "\nNo home games this week."

    lines = [format_game_line(g) for g in games]
    return header + "\n" + "\n".join(lines)


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

    start_date, end_date = get_week_range()
    print(f"Fetching Dodgers schedule for {start_date} to {end_date}...")

    try:
        data = fetch_schedule(start_date, end_date)
    except Exception as e:
        print(f"Error fetching MLB schedule: {e}", file=sys.stderr)
        sys.exit(1)

    games = parse_home_games(data)
    message = format_message(start_date, end_date, games)
    print(f"Sending weekly summary:\n{message}")
    send_sms(message, gmail_address, app_password, sms_address)
    print("SMS sent.")


if __name__ == "__main__":
    main()
