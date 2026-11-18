# Nifty Level + Alert Bot (free, runs in the cloud)

Calculates the day's Nifty 50 support/resistance levels automatically, puts
them on your phone as native Kite alerts, and sends price-action signals to
Telegram. It runs free on **GitHub Actions**, so no PC needs to be on: you
control everything from your iPad or phone.

It costs nothing: the free **Kite Connect Personal** API (alerts only), free
**Yahoo Finance** data (prices), and GitHub's free runners.

It never places, modifies, or cancels orders.

## Your day

| Time (IST) | What happens |
|---|---|
| ~08:30 | **Morning brief on Telegram**: previous day H/L/C, CPR (narrow = trend day, wide = range day), bias, nearest resistance/support zones with confluence stars, playbook. |
| ~08:31 | **Login message on Telegram.** Tap *Log in to Kite*, log in, then tap **Send to bot**. That's your only daily task. |
| 09:17 | Kite alerts are created around the live price (4 above, 4 below). The Kite app pushes to you when one is crossed. If you log in later, alerts are set the moment you do. |
| 09:15–15:30 | Every 15 min, Telegram signals for **ORB breaks**, **level breaks** (15m close through a zone), **rejection wicks**, and **momentum candles**. When a Kite alert fires, Telegram adds context. |
| 15:30 | Bot alerts are deleted and a day summary is sent. |

Skip the login and you still get the brief and all Telegram signals; only
the Kite alerts are skipped.

**Telegram commands:** `/levels` resends the levels, `/alerts` resets the Kite
alerts around the current price, `/status`, `/login`, `/help`.

GitHub's scheduler can start a few minutes late at busy times, which is why
the morning run is set for 08:30.

## How levels are built

From the previous day's candle and recent history: previous day
high/low/close, classic pivots (P, R1–R3, S1–S3), CPR (TC/BC), Camarilla
(H3/H4/L3/L4), previous week high/low, 30-day swing highs/lows and round
numbers. Levels within 15 points merge into one zone; zones built from several
sources get more stars, and those are the strongest levels.

## One-time setup on iPad (about 25 minutes, all in Safari + Telegram)

### 1. Telegram bot
1. In Telegram open **@BotFather** → `/newbot` → pick a name and a username ending in `bot`.
2. Save the **token** and the **username** (for example `ManjitNiftyBot`).
3. Open your new bot and tap **Start**.
4. Open **@userinfobot** and tap Start. It replies with your **Id** (a number). That's your chat id.

### 2. GitHub repository
1. Create a free account at github.com if you don't have one.
2. Create a **public** repository named `nifty-alert-bot` (public repos get
   unlimited free Actions minutes; the bot runs ~6.5 hours a day, which is more
   than the free private-repo allowance). Your keys are stored as encrypted
   Secrets, never in the code, and the Kite token is encrypted at rest.
3. Upload this project's files (or let Claude push them for you).

### 3. Login page (GitHub Pages)
Repo **Settings → Pages** → Source: *Deploy from a branch* → Branch `main`,
folder **/docs** → Save. After a minute your page is live at
`https://<your-github-username>.github.io/nifty-alert-bot/`.

### 4. Kite Connect Personal app (free)
1. Go to **developers.kite.trade**, log in with your Zerodha ID, and choose the **Personal (free)** plan.
2. **My Apps → Create new app**, type Personal.
3. **Redirect URL:** `https://<your-github-username>.github.io/nifty-alert-bot/`
4. Save the **API key** and **API secret**.

### 5. Secrets
Repo **Settings → Secrets and variables → Actions → New repository secret**.
Add these five:

| Name | Value |
|---|---|
| `KITE_API_KEY` | from step 4 |
| `KITE_API_SECRET` | from step 4 |
| `TELEGRAM_BOT_TOKEN` | from step 1 |
| `TELEGRAM_CHAT_ID` | your Id from @userinfobot |
| `TELEGRAM_BOT_USERNAME` | your bot's username, without @ |

### 6. Test
Repo **Actions** tab → enable workflows if asked → **Nifty bot → Run
workflow** → part `morning`. Within a minute you should get the brief and the
login message on Telegram. Log in and tap *Send to bot*; you should see
"Kite login OK". Cancel the run from the Actions tab when you're done testing
(outside market hours it waits until 14:10).

From then on it runs by itself every weekday.

## Keeping it alive

GitHub pauses scheduled workflows in a repository with no activity for 60
days, and emails you first. If that happens, open the Actions tab and click
**Enable workflow**, or make any small edit to the repo every couple of months.

## Safety and limits

- **No orders.** The bot only creates, reads and deletes Kite *alerts*.
- It only deletes alerts whose name starts with `NB `. Your own alerts are never touched.
- It only obeys Telegram messages from your chat id; anyone else messaging the bot is ignored.
- The Kite access token is encrypted (key derived from your API secret) before it's saved between runs, and it expires every morning anyway.
- Yahoo intraday candles are free but can lag by 1–2 minutes. Treat Telegram
  signals as heads-ups and confirm on the Kite chart. Kite alerts themselves
  use Zerodha's live price.
- Market holidays: if there are no candles by 09:40, the bot says so and stops for the day.
- These are levels and signals, not trade recommendations.

## Tuning (optional repository Variables or `.env`)

- `ALERTS_EACH_SIDE=4`: Kite alerts above and below price.
- `MERGE_DISTANCE=15`: points within which levels merge into one zone.
- `MAX_DISTANCE_PCT=2.0`: ignore levels farther than this from price.
- `BREAK_BUFFER=5`: a 15m close must clear a zone by this many points to count as a break.

## Running on a PC instead (optional)

Copy `.env.example` to `.env`, set the Kite app's Redirect URL to
`http://127.0.0.1:8765/callback`, then `pip install -r requirements.txt` and
`python run.py day` (Task Scheduler: `start_day.bat`; Mac cron: `start_day.sh`).

## Troubleshooting

- **No Telegram messages:** check the `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets, and that you tapped Start in your bot.
- **Login page says "No valid login":** the Kite app's Redirect URL must exactly match your GitHub Pages address. Send `/login` for a fresh link (request tokens expire within minutes).
- **"Send to bot" doesn't open Telegram:** tap *Copy token* and paste it into your bot chat.
- **"Insufficient permission" on alerts:** log in again with `/login`.
- **No signals:** signals only fire on actual breaks/rejections; a quiet day can have none.
