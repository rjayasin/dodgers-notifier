# dodgers-notifier

A GitHub Actions workflow that runs every morning and texts you if the Dodgers are playing a home game that day.

## How It Works

1. **GitHub Actions cron** triggers the workflow at 7:00 AM PDT / 6:00 AM PST every day.
2. **`check_game.py`** queries the free, unauthenticated [MLB Stats API](https://statsapi.mlb.com) for the Dodgers' schedule on today's date (in Pacific Time).
3. The script checks whether any game is a **home game at Dodger Stadium** — it verifies both the home team ID (119) and venue ID (22) to correctly exclude neutral-site games like the London or Tokyo Series.
4. Postponed games are skipped automatically. Double-headers trigger one SMS per game.
5. If a home game is found, the script **sends an email via Gmail SMTP** to your carrier's email-to-SMS gateway address (e.g. `5551234567@tmomail.net`). Your carrier converts that email into a text message delivered to your phone.

No paid services, no third-party accounts — just a Gmail account and GitHub.

---

## Carrier SMS Gateway Reference

Find your carrier below and note the gateway domain for the setup step.

| Carrier | SMS Gateway | MMS Gateway |
|---------|-------------|-------------|
| T-Mobile | `@tmomail.net` | `@tmomail.net` |
| Verizon | `@vtext.com` | `@vzwpix.com` |
| AT&T | `@txt.att.net` | `@mms.att.net` |
| Boost Mobile | `@sms.myboostmobile.com` | `@myboostmobile.com` |
| Cricket Wireless | `@sms.cricketwireless.net` | `@mms.cricketwireless.net` |
| Metro by T-Mobile | `@mymetropcs.com` | `@mymetropcs.com` |
| US Cellular | `@email.uscc.net` | `@mms.uscc.net` |
| Google Fi | `@msg.fi.google.com` | `@msg.fi.google.com` |
| Straight Talk | — | `@mypixmessages.com` |

> **AT&T note**: The legacy `@txt.att.net` gateway has reliability issues. Use `@mms.att.net` for better delivery.

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

### 4. Find your SMS gateway address

Using the table above, combine your 10-digit phone number with your carrier's SMS gateway domain:

```
5551234567@tmomail.net       ← T-Mobile example
5551234567@vtext.com         ← Verizon example
5551234567@mms.att.net       ← AT&T example
```

### 5. Add GitHub Actions secrets

In your GitHub repo:

1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** for each of the following:

| Secret name | Value |
|-------------|-------|
| `GMAIL_ADDRESS` | Your Gmail address (e.g. `yourname@gmail.com`) |
| `GMAIL_APP_PASSWORD` | The 16-character App Password from step 3 |
| `SMS_ADDRESS` | Your SMS gateway address from step 4 |

### 6. Enable the workflow

1. Go to the **Actions** tab in your repo.
2. If prompted with "Workflows aren't running", click **I understand my workflows, go ahead and enable them**.

### 7. Test it

1. In the **Actions** tab, select **Dodgers Home Game Check** from the left sidebar.
2. Click **Run workflow → Run workflow**.
3. Watch the run complete — if today is a Dodgers home game you'll get a text within a minute or two. If not, the run will exit cleanly with "No Dodgers home game today."

To test against a known game date locally:

```bash
GMAIL_ADDRESS=you@gmail.com \
GMAIL_APP_PASSWORD=your_app_password \
SMS_ADDRESS=5551234567@tmomail.net \
GAME_DATE=2025-07-04 \
python check_game.py
```

---

---

## Customization

**Change the notification time**: Edit the `cron` value in `.github/workflows/check_game.yml`. The schedule is in UTC — [crontab.guru](https://crontab.guru) is helpful for conversions.

**Notify multiple people**: Add additional secrets (e.g. `SMS_ADDRESS_2`) and call `send_sms()` once per recipient in `check_game.py`.

**Change the team**: Update `DODGERS_TEAM_ID` and `DODGER_STADIUM_VENUE_ID` in `check_game.py`. Team IDs and venue IDs can be looked up via the MLB Stats API: `https://statsapi.mlb.com/api/v1/teams?sportId=1`.
