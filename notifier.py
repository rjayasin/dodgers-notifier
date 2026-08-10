import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from zoneinfo import ZoneInfo

DODGERS_TEAM_ID = 119
DODGER_STADIUM_VENUE_ID = 22
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_SEASONS_URL = "https://statsapi.mlb.com/api/v1/seasons"
PT = ZoneInfo("America/Los_Angeles")


# ── Shared helpers ──────────────────────────────────────────────────

def fetch_schedule(**params: str) -> dict:
    base_params = f"sportId=1&teamId={DODGERS_TEAM_ID}&hydrate=team,venue"
    extra = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{MLB_SCHEDULE_URL}?{base_params}&{extra}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def send_email(
    subject: str,
    body: str,
    gmail_address: str,
    app_password: str,
    to_address: str,
    html_body: str | None = None,
) -> None:
    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    else:
        msg = MIMEText(body)
    msg["From"] = gmail_address
    msg["To"] = to_address
    msg["Subject"] = subject
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, to_address, msg.as_string())


def load_config() -> tuple[str, str, str]:
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    # Defaults to sending the notification to the same Gmail account it's sent from.
    notify_email = os.environ.get("NOTIFY_EMAIL") or gmail_address

    if not all([gmail_address, app_password]):
        print("Error: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set.", file=sys.stderr)
        sys.exit(1)

    return gmail_address, app_password, notify_email


def is_home_game(game: dict) -> bool:
    if game.get("status", {}).get("detailedState") == "Postponed":
        return False
    is_home = game["teams"]["home"]["team"]["id"] == DODGERS_TEAM_ID
    at_dodger_stadium = game.get("venue", {}).get("id") == DODGER_STADIUM_VENUE_ID
    return is_home and at_dodger_stadium


# ── Daily check ─────────────────────────────────────────────────────

def get_today_pt() -> str:
    raw = os.environ.get("GAME_DATE")
    if raw:
        return raw
    return datetime.now(PT).strftime("%Y-%m-%d")


def find_home_games(data: dict) -> list[dict]:
    if not data.get("dates"):
        return []
    return [g for g in data["dates"][0]["games"] if is_home_game(g)]


def format_message(game: dict) -> str:
    opponent = game["teams"]["away"]["team"]["name"]
    game_time = datetime.fromisoformat(game["gameDate"]).astimezone(PT)
    start_time = game_time.strftime("%-I:%M %p PT")
    return f"Dodgers home game at {start_time} vs {opponent}"


def daily() -> None:
    gmail_address, app_password, notify_email = load_config()

    date = get_today_pt()
    print(f"Checking MLB schedule for {date}...")

    try:
        data = fetch_schedule(date=date)
    except Exception as e:
        print(f"Error fetching MLB schedule: {e}", file=sys.stderr)
        sys.exit(1)

    home_games = find_home_games(data)

    if not home_games:
        print("No Dodgers home game today.")
        return

    for game in home_games:
        message = format_message(game)
        print(f"Home game found! Sending email:\n{message}")
        send_email(f"⚾ {message}", message, gmail_address, app_password, notify_email)
        print("Email sent.")


# ── Weekly schedule ─────────────────────────────────────────────────

def get_week_range() -> tuple[str, str]:
    """Return (start, end) as YYYY-MM-DD strings for Mon-Sun of the coming week."""
    today = datetime.now(PT).date()
    # days_until_monday: if today is Sunday (weekday=6), next Monday is tomorrow
    days_until_monday = (7 - today.weekday()) % 7 or 7
    monday = today + timedelta(days=days_until_monday)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def is_in_season(week_start: str, week_end: str) -> bool:
    """True if the Mon-Sun week overlaps the MLB season (regular season through postseason).

    Gates the "no games this week" email so it isn't sent every week of the offseason.
    Spring training weeks count as offseason since Dodger Stadium hosts no games then.
    """
    url = f"{MLB_SEASONS_URL}?sportId=1&season={week_start[:4]}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        seasons = json.loads(resp.read()).get("seasons", [])
    if not seasons:
        return False
    season = seasons[0]
    start = season.get("regularSeasonStartDate") or season.get("seasonStartDate")
    end = season.get("postSeasonEndDate") or season.get("seasonEndDate")
    if not (start and end):
        return False
    return week_start <= end and week_end >= start


def format_week_range(start_date: str, end_date: str) -> str:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if start.month == end.month:
        return f"{start.strftime('%b %-d')}–{end.strftime('%-d')}"
    return f"{start.strftime('%b %-d')}–{end.strftime('%b %-d')}"


def parse_home_games(data: dict) -> list[dict]:
    games = []
    for date_entry in data.get("dates", []):
        for game in date_entry["games"]:
            if is_home_game(game):
                games.append(game)
    return games


def game_columns(game: dict) -> tuple[str, str, str]:
    """Split a game into its (day, opponent, start time) columns."""
    opponent = game["teams"]["away"]["team"]["name"]
    game_time = datetime.fromisoformat(game["gameDate"]).astimezone(PT)
    day = game_time.strftime("%a %-m/%-d")
    start_time = game_time.strftime("%-I:%M %p")
    return day, opponent, start_time


def format_schedule_text(games: list[dict]) -> str:
    """Plain-text schedule, columns padded so they line up in a monospace client."""
    rows = [game_columns(g) for g in games]
    day_width = max(len(day) for day, _, _ in rows)
    opponent_width = max(len(opponent) for _, opponent, _ in rows)
    return "\n".join(
        f"{day:<{day_width}}  🆚 {opponent:<{opponent_width}}  {start_time}"
        for day, opponent, start_time in rows
    )


def format_schedule_html(games: list[dict]) -> str:
    """HTML schedule table; viewport meta and text-size-adjust stop mobile font boosting."""
    cell = 'style="padding:3px 8px 3px 0;white-space:nowrap"'
    rows = "".join(
        f"<tr><td {cell}>{escape(day)}</td>"
        f"<td {cell}>🆚 {escape(opponent)}</td>"
        f"<td {cell}>{escape(start_time)}</td></tr>"
        for day, opponent, start_time in (game_columns(g) for g in games)
    )
    body_style = (
        "margin:0;font-family:Arial,Helvetica,sans-serif;font-size:13px;"
        "-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%"
    )
    return (
        "<html><head>"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "</head>"
        f'<body style="{body_style}">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'border="0" style="border-collapse:collapse">'
        f"{rows}</table>"
        "</body></html>"
    )


def weekly() -> None:
    gmail_address, app_password, notify_email = load_config()

    start_date, end_date = get_week_range()
    print(f"Fetching Dodgers schedule for {start_date} to {end_date}...")

    try:
        data = fetch_schedule(startDate=start_date, endDate=end_date)
    except Exception as e:
        print(f"Error fetching MLB schedule: {e}", file=sys.stderr)
        sys.exit(1)

    games = parse_home_games(data)
    week_range = format_week_range(start_date, end_date)

    if not games:
        print("No Dodgers home games this week.")
        try:
            in_season = is_in_season(start_date, end_date)
        except Exception as e:
            print(f"Warning: could not determine season window ({e}); skipping email.", file=sys.stderr)
            return
        if not in_season:
            print("Offseason week — skipping email.")
            return
        subject = f"⚾ No Dodgers home games this week ({week_range})"
        print(f"Sending email:\n{subject}")
        send_email(subject, f"No Dodgers home games this week ({week_range}).", gmail_address, app_password, notify_email)
        print("Email sent.")
        return

    subject = f"⚾ {len(games)} Dodgers home games this week ({week_range})"
    body = format_schedule_text(games)
    print(f"Sending email:\n{subject}\n{body}")
    send_email(subject, body, gmail_address, app_password, notify_email, html_body=format_schedule_html(games))
    print("Email sent.")


# ── CLI entry point ─────────────────────────────────────────────────

COMMANDS = {"daily": daily, "weekly": weekly}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python notifier.py <{'|'.join(COMMANDS)}>", file=sys.stderr)
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
