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
# A game in one of these states isn't being played on the date it's listed
# under: postponed games come back with a new one, cancelled games not at all.
# The postseason usually drops a game the series didn't need rather than
# cancelling it, but a game still on the schedule and marked cancelled is one
# nobody should be emailed about either.
SKIPPED_GAME_STATES = {"Postponed", "Cancelled"}
# Stands in for first pitch while MLB still has the time as TBD, which the
# postseason spends days at a stretch doing.
TBD_TIME = "TBD"
# Marks a postseason game that's only played if the series runs that long.
IF_NECESSARY_NOTE = "(if necessary)"
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
    if game.get("status", {}).get("detailedState") in SKIPPED_GAME_STATES:
        return False
    # Both checks also throw out the unassigned bracket MLB publishes before the
    # postseason field is known: those games carry placeholder teams ("NL Wild
    # Card #1") at placeholder venues ("NL Stadium"), neither of which is ours.
    is_home = game["teams"]["home"]["team"]["id"] == DODGERS_TEAM_ID
    at_dodger_stadium = game.get("venue", {}).get("id") == DODGER_STADIUM_VENUE_ID
    return is_home and at_dodger_stadium


def is_if_necessary(game: dict) -> bool:
    """True for a postseason game that's played only if the series goes that far.

    MLB posts every game of a series up front and drops the ones the series ends
    without needing, so a game flagged here may simply be gone from the next
    fetch. Regular season games are never flagged, which is what keeps this
    invisible for all but a few weeks of the year.
    """
    return game.get("ifNecessary") == "Y"


def start_time_pt(game: dict) -> str | None:
    """First pitch in Pacific, or None while MLB still has the time as TBD.

    Postseason games are scheduled before their start times are set and carry a
    placeholder gameDate until then — printing it would announce a first pitch
    just after midnight, so callers say TBD instead.
    """
    if game.get("status", {}).get("startTimeTBD"):
        return None
    return datetime.fromisoformat(game["gameDate"]).astimezone(PT).strftime("%-I:%M %p")


def game_date(game: dict) -> str:
    """The game's date at Dodger Stadium, as YYYY-MM-DD.

    officialDate is what MLB files the game under, and it's right even for a
    postseason game whose placeholder start time hasn't been replaced yet.
    """
    scheduled = game.get("officialDate")
    if scheduled:
        return scheduled
    return datetime.fromisoformat(game["gameDate"]).astimezone(PT).strftime("%Y-%m-%d")


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
    """The daily alert, in one line.

    An "if necessary" postseason game says nothing about being conditional: by
    the morning of, the series has either reached it or MLB has taken it off the
    schedule, and only the former gets this far.
    """
    opponent = game["teams"]["away"]["team"]["name"]
    start_time = start_time_pt(game)
    if start_time is None:
        return f"Dodgers home game vs {opponent} (start time {TBD_TIME})"
    return f"Dodgers home game at {start_time} PT vs {opponent}"


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


def season_dates(year: str) -> tuple[str, str, str]:
    """(regular season start, regular season end, last day of the postseason)."""
    url = f"{MLB_SEASONS_URL}?sportId=1&season={year}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        seasons = json.loads(resp.read()).get("seasons", [])
    if not seasons:
        raise ValueError(f"MLB lists no season for {year}")
    season = seasons[0]
    start = season.get("regularSeasonStartDate") or season.get("seasonStartDate")
    regular_end = season.get("regularSeasonEndDate") or season.get("seasonEndDate")
    end = season.get("postSeasonEndDate") or season.get("seasonEndDate")
    if not (start and regular_end and end):
        raise ValueError(f"MLB's {year} season is missing its start or end dates")
    return start, regular_end, end


def dodgers_are_scheduled(start_date: str, end_date: str) -> bool:
    """True if the Dodgers have anything on the schedule in the span, home or away."""
    data = fetch_schedule(startDate=start_date, endDate=end_date)
    return any(date_entry.get("games") for date_entry in data.get("dates", []))


def is_in_season(week_start: str, week_end: str) -> bool:
    """True if a "no home games this week" email is worth sending for the week.

    Gates that email so it isn't sent every week of the offseason. Spring
    training weeks count as offseason since Dodger Stadium hosts no games then.

    Past the regular season the calendar stops being enough. October is only
    baseball season for a fan of a team still in it, so a postseason week has to
    find the Dodgers themselves on the schedule: MLB holds their bracket slots
    while they're alive and drops them once they're out, so the weekly email
    ends with their season instead of running through a World Series they aren't
    in. The trade is that the few hours between a series ending and the next
    round being assigned read as over — a Sunday run landing in that gap stays
    quiet for the week, which the daily check still covers game by game.
    """
    start, regular_end, end = season_dates(week_start[:4])
    if week_start > end:
        return False
    if week_end < start:
        return False
    if week_start <= regular_end:
        return True
    return dodgers_are_scheduled(week_start, end)


def format_week_range(start_date: str, end_date: str) -> str:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    if start.month == end.month:
        return f"{start.strftime('%b %-d')}–{end.strftime('%-d')}"
    return f"{start.strftime('%b %-d')}–{end.strftime('%b %-d')}"


def schedule_entry(game: dict) -> dict:
    """One game, formatted for display. Start times are rendered in Pacific so
    first pitch reads as announced rather than in the reader's own timezone."""
    date = game_date(game)
    entry = {
        "date": date,
        "day": datetime.strptime(date, "%Y-%m-%d").strftime("%a %-m/%-d"),
        "time": start_time_pt(game) or TBD_TIME,
        "opponent": game["teams"]["away"]["team"]["name"],
    }
    # Left off entirely rather than written as a false into every row: only a
    # handful of postseason games a year are conditional, and the dashboard
    # treats the missing key as "this game is happening".
    if is_if_necessary(game):
        entry["if_necessary"] = True
    return entry


def game_columns(game: dict) -> tuple[str, str, str]:
    """Split a game into its (day, start time, opponent) email columns."""
    entry = schedule_entry(game)
    opponent = entry["opponent"]
    if entry.get("if_necessary"):
        opponent = f"{opponent} {IF_NECESSARY_NOTE}"
    return entry["day"], f"@ {entry['time']}", opponent


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


def count_of(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def format_week_subject(games: list[dict], week_range: str) -> str:
    """The weekly email's subject line.

    Conditional postseason games are counted apart from the rest rather than
    folded into one total. A series that ends early takes them off the schedule,
    and a subject promising four home games in a week that plays two is worse
    than one that promises two and adds the other two as a maybe.
    """
    conditional = sum(1 for g in games if is_if_necessary(g))
    confirmed = len(games) - conditional
    if not confirmed:
        return f"⚾ {count_of(conditional, 'possible Dodgers home game')} this week ({week_range})"
    subject = f"⚾ {count_of(confirmed, 'Dodgers home game')} this week"
    if conditional:
        subject += f", {conditional} if necessary"
    return f"{subject} ({week_range})"


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


def unscheduled_span(window_start: str, played_dates: set[str]) -> tuple[str, str] | None:
    """The (first, last) dates whose games the postseason hasn't assigned yet.

    An empty week means one thing in June — the Dodgers are on the road — and
    another in October, where it usually means the bracket simply hasn't reached
    them. The dashboard has to say which, so the span past the regular season is
    marked, but only while the Dodgers still have a game ahead of them: once
    they're eliminated MLB stops filling their slots and the empty weeks are
    empty for good.
    """
    try:
        _, regular_end, season_end = season_dates(window_start[:4])
    except Exception as e:
        print(f"Warning: could not determine season window ({e}); "
              "empty postseason weeks will read as having no home games.", file=sys.stderr)
        return None
    today = datetime.now(PT).strftime("%Y-%m-%d")
    if not any(date >= today for date in played_dates):
        return None
    # The day after the regular season's last, so a September week that happens
    # to end on it isn't read as waiting on a bracket that hasn't started.
    postseason_start = (
        datetime.strptime(regular_end, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")
    return max(postseason_start, today), season_end


def load_published_weeks(path: str) -> list[dict] | None:
    """The weeks already published, or None if there's no readable file yet."""
    try:
        with open(path) as f:
            return json.load(f).get("weeks")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_schedule_json(window_start: str, games: list[dict], played_dates: set[str]) -> None:
    """Write docs/schedule.json — the home games behind the Pages dashboard.

    PUBLISHED_WEEKS consecutive weeks are written, starting from the Monday
    given in window_start. The dashboard opens on whichever contains today, so
    it spends the whole week on the current week rather than jumping ahead the
    moment a run lands — a missed run still leaves it a week to fall back on —
    and its arrows browse the later weeks from there.

    played_dates is every date the Dodgers play on, away games included, which
    is what separates a week they spend on the road from one the postseason
    hasn't filled in yet.
    """
    path = os.environ.get("SCHEDULE_JSON_PATH", SCHEDULE_JSON_PATH)
    entries = [schedule_entry(g) for g in games]
    unscheduled = unscheduled_span(window_start, played_dates)

    monday = datetime.strptime(window_start, "%Y-%m-%d").date()
    weeks = []
    for offset in range(0, 7 * PUBLISHED_WEEKS, 7):
        start = (monday + timedelta(days=offset)).strftime("%Y-%m-%d")
        end = (monday + timedelta(days=offset + 6)).strftime("%Y-%m-%d")
        week = {
            "start": start,
            "end": end,
            "range": format_week_range(start, end),
            "games": [e for e in entries if start <= e["date"] <= end],
        }
        # A week the Dodgers play in is scheduled whether or not any of it is at
        # home, so only a week with nothing at all in it can be waiting on the
        # bracket.
        if (not any(start <= date <= end for date in played_dates)
                and unscheduled and start <= unscheduled[1] and end >= unscheduled[0]):
            week["pending"] = True
        weeks.append(week)

    if load_published_weeks(path) == weeks:
        # Rewriting would only bump generated_at, and the workflow commits on any
        # diff — the daily run would redeploy the site every morning for nothing.
        print(f"Schedule unchanged — {path} left as it is.")
        return

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


def refresh_schedule() -> list[dict]:
    """Publish docs/schedule.json for the window, and hand back its home games.

    Runs daily rather than only on Sundays: the regular season schedule is set
    months out, but the postseason fills itself in a round at a time, and a
    dashboard that only refreshed on Sunday would spend October up to six days
    behind the bracket.
    """
    today = datetime.now(PT).date()
    # The dashboard browses weeks the email doesn't cover, so fetch the whole
    # published window from this week's Monday and let the email take its slice.
    window_start, window_end = week_window(
        (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    )
    print(f"Fetching Dodgers schedule for {window_start} to {window_end}...")

    try:
        data = fetch_schedule(startDate=window_start, endDate=window_end)
    except Exception as e:
        print(f"Error fetching MLB schedule: {e}", file=sys.stderr)
        sys.exit(1)

    all_games = [g for date_entry in data.get("dates", []) for g in date_entry.get("games", [])]
    home_games = [g for g in all_games if is_home_game(g)]
    write_schedule_json(window_start, home_games, {game_date(g) for g in all_games})
    return home_games


def schedule() -> None:
    """Refresh the dashboard's schedule without sending anything."""
    refresh_schedule()


def weekly() -> None:
    gmail_address, app_password, notify_email = load_config()

    start_date, end_date = get_week_range()
    # Refreshed before the email branches so the dashboard is republished even
    # on weeks where nothing goes out (no home games, or the offseason gate).
    window_games = refresh_schedule()

    games = [g for g in window_games if start_date <= game_date(g) <= end_date]
    week_range = format_week_range(start_date, end_date)

    if not games:
        print("No Dodgers home games this week.")
        try:
            in_season = is_in_season(start_date, end_date)
        except Exception as e:
            print(f"Warning: could not determine season window ({e}); skipping email.", file=sys.stderr)
            return
        if not in_season:
            print("Nothing left of the Dodgers' season this week — skipping email.")
            return
        subject = f"⚾ No Dodgers home games this week ({week_range})"
        print(f"Sending email:\n{subject}")
        body = f"No Dodgers home games this week ({week_range}).\n\n{dashboard_link_text()}"
        send_email(subject, body, gmail_address, app_password, notify_email)
        print("Email sent.")
        return

    subject = format_week_subject(games, week_range)
    body = format_schedule_text(games)
    print(f"Sending email:\n{subject}\n{body}")
    send_email(subject, body, gmail_address, app_password, notify_email, html_body=format_schedule_html(games))
    print("Email sent.")


# ── Workflow run history ────────────────────────────────────────────

# Actions sets GITHUB_REPOSITORY itself, so a fork records its own runs without
# editing anything; the literal is only for running this by hand.
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY") or "rjayasin/dodgers-notifier"
GITHUB_RUNS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs"
# The dashboard charts only these two, so only these two are worth storing.
# Site deploys, Pages builds and Keep Alive would pad the file for nothing.
DASHBOARD_WORKFLOWS = {"Dodgers Daily Check", "Dodgers Weekly Schedule"}
# The Pages dashboard reads this file; the daily workflow commits it back to the repo.
RUNS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "runs.json")
RUNS_PER_PAGE = 100
# A backstop for the first backfill only. GitHub stops listing past 1,000 runs
# anyway, so this can't cut a genuine catch-up short.
MAX_RUN_PAGES = 10


def github_get(url: str) -> dict:
    """GET the GitHub REST API, authenticated when a token is in the environment.

    Anonymous calls work against a public repo but share a 60/hour budget with
    every other job on the runner's IP, so Actions passes GITHUB_TOKEN.
    """
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.loads(resp.read())


def run_record(run: dict) -> dict:
    """The slice of a workflow run the dashboard actually draws.

    html_url is left out on purpose: the page rebuilds it from the id, and at a
    run a day the repeated prefix would soon outweigh the data around it.
    """
    return {
        "id": run["id"],
        "name": run["name"],
        "run_number": run["run_number"],
        "event": run["event"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "run_started_at": run.get("run_started_at") or run["created_at"],
        "updated_at": run["updated_at"],
    }


def load_run_history(path: str) -> dict[int, dict]:
    """The runs already committed, keyed by id. Missing file means first run."""
    try:
        with open(path) as f:
            stored = json.load(f)
    except FileNotFoundError:
        return {}
    return {r["id"]: r for r in stored.get("runs", [])}


def fetch_run_history(known: dict[int, dict]) -> dict[int, dict]:
    """Page back through the run list until a page holds nothing new.

    Runs come back newest first, so a page whose every run already matches what
    is stored means the pages behind it match too. In steady state that settles
    the daily catch-up in two requests, while an empty history still walks back
    to the oldest run GitHub still lists.

    A page with no dashboard runs on it at all decides nothing — a burst of
    Pages builds can fill one — so paging continues through it.
    """
    # The recording run is still in flight, so its own row would be stored
    # half-finished and stay that way until the next day corrected it. Leaving
    # it out costs a day's latency and keeps the file to completed runs.
    self_run_id = int(os.environ.get("GITHUB_RUN_ID") or 0)
    found: dict[int, dict] = {}

    for page in range(1, MAX_RUN_PAGES + 1):
        data = github_get(f"{GITHUB_RUNS_URL}?per_page={RUNS_PER_PAGE}&page={page}")
        runs = data.get("workflow_runs", [])
        if not runs:
            break
        records = {
            r["id"]: run_record(r) for r in runs
            if r["name"] in DASHBOARD_WORKFLOWS and r["id"] != self_run_id
        }
        found.update(records)
        # `!=` and not `not in`: a run listed before it finished has to be
        # picked up again once its conclusion lands.
        if records and all(known.get(rid) == rec for rid, rec in records.items()):
            break

    return found


def write_run_history(path: str, records: dict[int, dict]) -> None:
    """Write docs/runs.json — the run history behind the Pages dashboard.

    Newest first, because the dashboard's table renders in file order and its
    "last run" stat takes the first completed row it finds.
    """
    runs = sorted(
        records.values(),
        key=lambda r: (r["run_started_at"], r["id"]),
        reverse=True,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": GITHUB_REPO,
        "runs": runs,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def runs() -> None:
    """Fold the newest workflow runs into docs/runs.json.

    The dashboard used to call the GitHub API from the browser on every visit,
    which spent the viewer's own anonymous rate limit and could only ever show
    the runs GitHub still had. Accumulating them here keeps the history past
    whatever GitHub drops, and costs the page one static file.
    """
    path = os.environ.get("RUNS_JSON_PATH", RUNS_JSON_PATH)
    known = load_run_history(path)
    print(f"Reading workflow runs for {GITHUB_REPO} ({len(known)} already stored)...")

    try:
        fetched = fetch_run_history(known)
    except Exception as e:
        print(f"Error fetching workflow runs: {e}", file=sys.stderr)
        sys.exit(1)

    added = sum(1 for run_id in fetched if run_id not in known)
    updated = sum(1 for run_id, rec in fetched.items()
                  if run_id in known and known[run_id] != rec)
    if not (added or updated) and os.path.exists(path):
        # Rewriting would only bump generated_at, and the workflow commits on any
        # diff — a daily no-op commit would redeploy the site for nothing. A repo
        # with no qualifying runs yet still falls through, so the dashboard gets
        # an empty file to read rather than a 404.
        print(f"No new runs — {path} left as it is ({len(known)} runs).")
        return

    merged = {**known, **fetched}
    write_run_history(path, merged)
    print(f"Wrote {path} ({len(merged)} runs, {added} new, {updated} updated)")


# ── CLI entry point ─────────────────────────────────────────────────

COMMANDS = {"daily": daily, "weekly": weekly, "schedule": schedule, "runs": runs}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python notifier.py <{'|'.join(COMMANDS)}>", file=sys.stderr)
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
