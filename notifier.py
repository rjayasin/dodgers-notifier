import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from zoneinfo import ZoneInfo

DODGERS_TEAM_ID = 119
DODGER_STADIUM_VENUE_ID = 22
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_SEASONS_URL = "https://statsapi.mlb.com/api/v1/seasons"
PT = ZoneInfo("America/Los_Angeles")
DASHBOARD_URL = "https://rjayasin.github.io/dodgers-notifier"
DASHBOARD_LINK_TEXT = "See the full schedule and recent runs on the dashboard"
# How many weeks docs/schedule.json publishes, starting from the current one.
# The dashboard's arrows browse this many weeks forward; roughly two months is
# far enough to plan around and still leaves the file a few KB.
PUBLISHED_WEEKS = 8
# The Pages dashboard reads this file; the weekly workflow commits it back to the repo.
SCHEDULE_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "schedule.json")


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


def game_date_pt(game: dict) -> str:
    """The game's date at Dodger Stadium, as YYYY-MM-DD."""
    return datetime.fromisoformat(game["gameDate"]).astimezone(PT).strftime("%Y-%m-%d")


def schedule_entry(game: dict) -> dict:
    """One game, formatted for display. Start times are rendered in Pacific so
    first pitch reads as announced rather than in the reader's own timezone."""
    game_time = datetime.fromisoformat(game["gameDate"]).astimezone(PT)
    return {
        "date": game_time.strftime("%Y-%m-%d"),
        "day": game_time.strftime("%a %-m/%-d"),
        "time": game_time.strftime("%-I:%M %p"),
        "opponent": game["teams"]["away"]["team"]["name"],
    }


def game_columns(game: dict) -> tuple[str, str, str]:
    """Split a game into its (day, start time, opponent) email columns."""
    entry = schedule_entry(game)
    return entry["day"], f"@ {entry['time']}", entry["opponent"]


def dashboard_link_html(font: str) -> str:
    """The dashboard link that closes the HTML email, in Dodger blue."""
    return (
        f'<p style="{font};margin:16px 0 0">'
        f'<a href="{DASHBOARD_URL}" style="color:#005A9C">'
        f"{DASHBOARD_LINK_TEXT}</a></p>"
    )


def dashboard_link_text() -> str:
    """The dashboard link that closes the plain-text email; the URL goes on its
    own line so clients that autolink don't swallow the trailing punctuation."""
    return f"{DASHBOARD_LINK_TEXT}:\n{DASHBOARD_URL}"


def format_schedule_text(games: list[dict]) -> str:
    """Plain-text schedule, columns padded so they line up in a monospace client."""
    rows = [game_columns(g) for g in games]
    day_width = max(len(day) for day, _, _ in rows)
    # Times are right-aligned so 10:10 AM and 7:10 PM share a right edge.
    time_width = max(len(start_time) for _, start_time, _ in rows)
    schedule = "\n".join(
        f"{day:<{day_width}}  {start_time:>{time_width}}  🆚 {opponent}"
        for day, start_time, opponent in rows
    )
    return f"{schedule}\n\n{dashboard_link_text()}"


def format_schedule_html(games: list[dict]) -> str:
    """HTML schedule table; viewport meta and text-size-adjust stop mobile font boosting."""
    # The font goes on every cell, not on <body>: clients routinely strip the
    # body tag, and without a doctype a table wouldn't inherit from it anyway.
    font = "font-family:Arial,Helvetica,sans-serif;font-size:14px"
    cell = f"{font};padding:3px 8px 3px 0;white-space:nowrap"
    # The last column carries no right padding — it only ate width a narrow
    # phone needs, since a 10:10 AM start pushes the widest row to the edge.
    last_cell = f"{font};padding:3px 0;white-space:nowrap"
    rows = "".join(
        f'<tr><td style="{cell}">{escape(day)}</td>'
        f'<td style="{cell};text-align:right">{escape(start_time)}</td>'
        f'<td style="{last_cell}">🆚 {escape(opponent)}</td></tr>'
        for day, start_time, opponent in (game_columns(g) for g in games)
    )
    body_style = (
        f"margin:0;{font};"
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
        f"{dashboard_link_html(font)}"
        "</body></html>"
    )


def week_window(window_start: str) -> tuple[str, str]:
    """The (first Monday, last Sunday) of the span docs/schedule.json covers."""
    monday = datetime.strptime(window_start, "%Y-%m-%d").date()
    last_sunday = monday + timedelta(days=7 * PUBLISHED_WEEKS - 1)
    return window_start, last_sunday.strftime("%Y-%m-%d")


def write_schedule_json(window_start: str, games: list[dict]) -> None:
    """Write docs/schedule.json — the home games behind the Pages dashboard.

    PUBLISHED_WEEKS consecutive weeks are written, starting from the Monday
    given in window_start. The dashboard opens on whichever contains today, so
    it spends the whole week on the current week rather than jumping ahead the
    moment Sunday's run lands — a missed run still leaves it a week to fall
    back on — and its arrows browse the later weeks from there.
    """
    path = os.environ.get("SCHEDULE_JSON_PATH", SCHEDULE_JSON_PATH)
    entries = [schedule_entry(g) for g in games]

    monday = datetime.strptime(window_start, "%Y-%m-%d").date()
    weeks = []
    for offset in range(0, 7 * PUBLISHED_WEEKS, 7):
        start = (monday + timedelta(days=offset)).strftime("%Y-%m-%d")
        end = (monday + timedelta(days=offset + 6)).strftime("%Y-%m-%d")
        weeks.append({
            "start": start,
            "end": end,
            "range": format_week_range(start, end),
            "games": [e for e in entries if start <= e["date"] <= end],
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weeks": weeks,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    total = sum(len(w["games"]) for w in weeks)
    print(f"Wrote {path} ({len(weeks)} weeks from {weeks[0]['range']}, {total} home games)")


def weekly() -> None:
    gmail_address, app_password, notify_email = load_config()

    start_date, end_date = get_week_range()
    # The dashboard browses weeks the email doesn't cover, so fetch the whole
    # published window from this week's Monday and let the email take its slice.
    today = datetime.now(PT).date()
    window_start, window_end = week_window(
        (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    )
    print(f"Fetching Dodgers schedule for {window_start} to {window_end}...")

    try:
        data = fetch_schedule(startDate=window_start, endDate=window_end)
    except Exception as e:
        print(f"Error fetching MLB schedule: {e}", file=sys.stderr)
        sys.exit(1)

    window_games = parse_home_games(data)
    # Written before the email branches so the dashboard is refreshed even on
    # weeks where no email goes out (no home games, or the offseason gate).
    write_schedule_json(window_start, window_games)

    games = [g for g in window_games if start_date <= game_date_pt(g) <= end_date]
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
        body = f"No Dodgers home games this week ({week_range}).\n\n{dashboard_link_text()}"
        send_email(subject, body, gmail_address, app_password, notify_email)
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
