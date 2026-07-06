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

### How delivery works

The script **sends an email via Gmail SMTP** from your Gmail account to the address in the `NOTIFY_EMAIL` secret (or back to the sending Gmail account itself if `NOTIFY_EMAIL` isn't set).

No paid services, no third-party accounts — just a Gmail account and GitHub.

> **Why not SMS?** Earlier versions texted via carrier email-to-SMS gateways (e.g. `@vtext.com`). Carriers are shutting those gateways down — Verizon retires `vtext.com`/`vzwpix.com` by March 31, 2027, and delivery is already unreliable, with messages arriving late, out of order, or not at all. Email is dependable and has no length limits. To get phone notifications, enable push notifications in the Gmail app for the recipient address (a Gmail filter can label these emails so you can create a distinct alert for them).

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
