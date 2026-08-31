# dodgers-notifier

A GitHub Actions automation that emails you about upcoming Dodgers home games — a daily game-day alert and a weekly schedule summary.

**[rjayasin.github.io/dodgers-notifier](https://rjayasin.github.io/dodgers-notifier)** — workflow run dashboard

## How It Works

Everything lives in a single script, `notifier.py`, with two subcommands:

### Daily check (`python notifier.py daily`)

1. **GitHub Actions cron** triggers the workflow at 7:00 AM PDT / 6:00 AM PST every day.
2. The script queries the free, unauthenticated [MLB Stats API](https://statsapi.mlb.com) for the Dodgers' schedule on today's date (in Pacific Time).
3. It checks whether any game is a **home game at Dodger Stadium** — it verifies both the home team ID (119) and venue ID (22) to correctly exclude neutral-site games like the London or Tokyo Series.
4. Postponed games are skipped automatically. Double-headers trigger one email per game.
5. If a home game is found, the script **sends an email** with the opponent and first pitch time.

### Weekly schedule (`python notifier.py weekly`)

1. **GitHub Actions cron** triggers the workflow at 4:00 PM PDT / 3:00 PM PST every Sunday.
2. The script fetches the Dodgers schedule for the upcoming Monday–Sunday week.
3. All home games are collected and formatted into a **single email** — the game count and week range in the subject line, one line per game in the body.
4. If there are **no home games that week**, you get a "No Dodgers home games this week" email instead.
5. An **offseason gate** skips that email outside the MLB season (Opening Day through the postseason), so you aren't emailed "no games" all winter.
6. The next eight weeks are written to `docs/schedule.json` and committed back to `main` — that's what the [dashboard](#dashboard) shows at the top of the page. The file is written before the email branches, so the dashboard refreshes even on weeks that send no email.

### How delivery works

The script **sends an email via Gmail SMTP** from your Gmail account to the address in the `NOTIFY_EMAIL` secret (or back to the sending Gmail account itself if `NOTIFY_EMAIL` isn't set).

No paid services, no third-party accounts — just a Gmail account and GitHub.

### What the emails look like

**Daily game-day alert** — subject and body are the same line:

> **⚾ Dodgers home game at 7:10 PM PT vs Kansas City Royals**
>
> Dodgers home game at 7:10 PM PT vs Kansas City Royals

**Weekly schedule** — the game count and week range in the subject, one line per game in the body, closing with a link to the [dashboard](https://rjayasin.github.io/dodgers-notifier):

> **⚾ 7 Dodgers home games this week (Aug 10–16)**
>
> ```
> Mon 8/10  @ 7:10 PM  🆚 Kansas City Royals
> Tue 8/11  @ 7:10 PM  🆚 Kansas City Royals
> Wed 8/12  @ 7:10 PM  🆚 Kansas City Royals
> Thu 8/13  @ 7:10 PM  🆚 Milwaukee Brewers
> Fri 8/14  @ 7:10 PM  🆚 Milwaukee Brewers
> Sat 8/15  @ 4:15 PM  🆚 Milwaukee Brewers
> Sun 8/16  @ 1:10 PM  🆚 Milwaukee Brewers
> ```
>
> See the full schedule and recent runs on the dashboard

The weekly email is sent as both HTML and plain text. The HTML part renders the schedule as a table so the columns line up in a proportional font; the plain-text part pads them to line up in a monospace client. Start times are Pacific.

**Weekly schedule, no home games** — sent only during the season:

> **⚾ No Dodgers home games this week (Aug 10–16)**
>
> No Dodgers home games this week (Aug 10–16).
>
> See the full schedule and recent runs on the dashboard

> **Why not SMS?** Earlier versions texted via carrier email-to-SMS gateways (e.g. `@vtext.com`). Carriers are shutting those gateways down — Verizon retires `vtext.com`/`vzwpix.com` by March 31, 2027, and delivery is already unreliable, with messages arriving late, out of order, or not at all. Email is dependable and has no length limits. To get phone notifications, enable push notifications in the Gmail app for the recipient address (a Gmail filter can label these emails so you can create a distinct alert for them).

---

## Dashboard

[rjayasin.github.io/dodgers-notifier](https://rjayasin.github.io/dodgers-notifier) is a static page served from `docs/` by the **Deploy GitHub Pages** workflow.

**Home game schedule** (top of the page) comes from `docs/schedule.json`, which `python notifier.py weekly` writes and the weekly workflow commits back to `main`:

```json
{
  "generated_at": "2026-08-09T23:00:12Z",
  "weeks": [
    {
      "start": "2026-08-10",
      "end": "2026-08-16",
      "range": "Aug 10–16",
      "games": [
        { "date": "2026-08-10", "day": "Mon 8/10", "time": "7:10 PM", "opponent": "Kansas City Royals" }
      ]
    },
    { "start": "2026-08-17", "end": "2026-08-23", "range": "Aug 17–23", "games": [] }
  ]
}
```

Eight consecutive weeks are published, starting with the current one (`PUBLISHED_WEEKS` in `notifier.py`) — about two months of home games in roughly 3 KB. The card opens on the week containing today, so it stays on the **current** week all week rather than jumping ahead the moment Sunday's run lands, and a missed Sunday run still leaves it a week to fall back on.

The **‹ ›** arrows beside the heading step through the published weeks. They stop at both ends — the range starts at the current week, so there is nothing behind it — and the heading names the week it lands on: *this week*, *next week*, then the date range alone.

Within a week, today's game is highlighted and games already played are greyed out, both judged against the current Pacific date. Start times are pre-formatted in Pacific rather than rendered from a timestamp, so first pitch reads the same wherever the page is opened.

**Workflow run stats and charts** below it are fetched live from the GitHub REST API in the browser; nothing about them is committed. The page covers the two notifier workflows named in `INCLUDED_WORKFLOWS` — Daily Check and Weekly Schedule — so site deploys, Pages builds and Keep Alive stay out of the charts and the run list. It's an include list rather than an exclude list because a new workflow should stay off the page until it's deliberately added. Manually triggered (`workflow_dispatch`) runs are filtered out in the same place, so they don't skew the completion-time charts.

Pages deploys on any push touching `docs/**`, and also when the weekly workflow completes — a push made with the workflow's `GITHUB_TOKEN` deliberately does not trigger `push` workflows, so the schedule commit needs that second trigger to reach the site.

---

## Setup

### 1. Fork or clone this repository

Make sure the repo lives under your own GitHub account so you can add secrets and the Actions workflow will run under your quota.

### 2. Enable 2-Step Verification on Gmail

Gmail App Passwords require 2-Step Verification to be active.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Under "How you sign in to Google", click **2-Step Verification** and follow the prompts to enable it.

### 3. Create a Gmail App Password

An App Password is a 16-character one-time token that lets the script authenticate with Gmail without exposing your real password.

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Under "App name", type something like `dodgers-notifier` and click **Create**.
3. Google displays the 16-character password **once** — copy it immediately.

### 4. Add GitHub Actions secrets

In your GitHub repo:

1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** for each of the following:

| Secret name | Value |
|-------------|-------|
| `GMAIL_ADDRESS` | Your Gmail address (e.g. `yourname@gmail.com`) |
| `GMAIL_APP_PASSWORD` | The 16-character App Password from step 3 |
| `NOTIFY_EMAIL` | *(optional)* Where to send notifications — any email address. Defaults to `GMAIL_ADDRESS` (the account emails itself) |

### 5. Enable the workflows

1. Go to the **Actions** tab in your repo.
2. If prompted with "Workflows aren't running", click **I understand my workflows, go ahead and enable them**.
3. Both workflows — **Dodgers Daily Check** (daily) and **Dodgers Weekly Schedule** (Sunday) — will start running on their cron schedules automatically.

### 6. Test it

**Test the daily check:**

1. In the **Actions** tab, select **Dodgers Daily Check** from the left sidebar.
2. Click **Run workflow → Run workflow**.
3. Watch the run complete — if today is a Dodgers home game you'll get an email within a minute or two. If not, the run will exit cleanly with "No Dodgers home game today."

**Test the weekly schedule:**

1. In the **Actions** tab, select **Dodgers Weekly Schedule** from the left sidebar.
2. Click **Run workflow → Run workflow**.
3. You'll receive one email with the upcoming week's home game schedule.

**Test locally against a known game date:**

```bash
GMAIL_ADDRESS=you@gmail.com \
GMAIL_APP_PASSWORD=your_app_password \
GAME_DATE=2025-07-04 \
python notifier.py daily
```

---

## Customization

**Change the notification time**: Edit the `cron` value in `.github/workflows/daily_check.yml` or `.github/workflows/weekly_schedule.yml`. The schedule is in UTC — [crontab.guru](https://crontab.guru) is helpful for conversions.

**Notify multiple people**: Add additional secrets (e.g. `NOTIFY_EMAIL_2`) and call `send_email()` once per recipient in `notifier.py`.

**Change the team**: Update `DODGERS_TEAM_ID` and `DODGER_STADIUM_VENUE_ID` in `notifier.py`. Team IDs and venue IDs can be looked up via the MLB Stats API: `https://statsapi.mlb.com/api/v1/teams?sportId=1`.
