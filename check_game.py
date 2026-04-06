import os
import sys
from datetime import datetime

from notifier import (
    DODGERS_TEAM_ID,
    DODGER_STADIUM_VENUE_ID,
    PT,
    fetch_schedule,
    load_config,
    send_sms,
)


def get_today_pt() -> str:
    raw = os.environ.get("GAME_DATE")
    if raw:
        return raw
    return datetime.now(PT).strftime("%Y-%m-%d")


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
    return (
        f"⚾ Dodgers home game today!\n"
        f"🆚 {opponent}\n"
        f"⏰ First pitch: {start_time}"
    )


def main() -> None:
    gmail_address, app_password, sms_address = load_config()

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
        print(f"Home game found! Sending SMS:\n{message}")
        send_sms(message, gmail_address, app_password, sms_address)
        print("SMS sent.")


if __name__ == "__main__":
    main()
