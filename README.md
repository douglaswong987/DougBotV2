# DougBot

A Discord bot for your server. Game stats tracking, reminders, fun commands, and more.

## Setup

### 1. Clone and install dependencies

```bash
git clone <your-repo>
cd DougBot
pip install -r requirements.txt
```

### 2. Configure your token

```bash
cp .env.example .env
# Edit .env and paste your bot token
```

> ⚠️ **Important:** The old token was hardcoded in source and committed to git.  
> Go to the [Discord Developer Portal](https://discord.com/developers/applications) → your app → Bot → **Reset Token** immediately.

### 3. Bot permissions

In the Developer Portal, enable these **Privileged Gateway Intents**:
- Server Members Intent
- Message Content Intent

Invite the bot with these scopes: `bot`, `applications.commands`  
Permissions: Send Messages, Embed Links, Read Message History, Manage Messages, View Audit Log

### 4. Run

```bash
python bot.py
```

The SQLite database (`dougbot.db`) is created automatically on first run.

---

## Commands

### Fun
| Command | Description |
|---|---|
| `/cock` | Generate your daily cock length |
| `/cockcharts` | Daily leaderboard |
| `/roll [max] [min]` | Roll a number (default 1–100) |
| `/cointoss` | Flip a coin |
| `/8ball <question>` | Ask the magic 8ball |

### Reminders
| Command | Description |
|---|---|
| `/remindme <event> <duration>` | Set a reminder (e.g. `2 hours`, `30 minutes`, `1 day`) |
| `/reminderslist` | List your active reminders |
| `/cancelevent <id>` | Cancel a reminder by ID |
| `/cancelall` | Cancel all your reminders |

### Admin
| Command | Description |
|---|---|
| `/purge <count>` | Delete N messages from the channel |
| `/logs set <#channel>` | Set where event logs are sent |
| `/logs clear` | Disable logging |
| `/logs status` | Show current log channel |
| `/insults adduser @user` | Add a user to the random insult pool |
| `/insults removeuser @user` | Remove a user |
| `/insults addrole @role` | Add a whole role |
| `/insults removerole @role` | Remove a role |
| `/insults list` | Show all current targets |

All commands also work with the `!` prefix.

## Migration from old bot

The old `cock_lengths` dict is gone — lengths now persist in SQLite across restarts.  
Reminders are persisted too, so they survive crashes and redeploys.

The hardcoded insult targets (role IDs in `constants.py`) are replaced by `/insults adduser` and `/insults addrole` commands stored in the DB.

The hardcoded log channel ID is replaced by `/logs set #channel`.

The concert command (`!concerts`) has been removed as requested.
