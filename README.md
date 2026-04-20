# Telegram Userbot Upgrade

This project upgrades the old single-user repost repo into a small multi-user Telegram bot platform.
It keeps the old repo's core repost ideas intact:
- pair-based reposting
- source -> target repost flow
- check/scan logic
- duplicate protection
- forward rule
- post rule
- ads
- keyword filters
- preview-post behavior

The control surface is now a Telegram bot UI for multiple users, while the repost runtime still uses **one shared Telethon StringSession** for the whole service.

## High-level architecture

The project runs as one practical Render service and is split into two logical layers inside one codebase.

### 1) Bot / UI layer
This layer uses the Telegram Bot API through `aiogram`.
It handles:
- `/start`
- OTP verification
- restore-or-fresh choice after expired access
- language selection
- tutorial/help
- pair creation, edit, and deletion
- keyword, ads, status, check, forward rule, post rule
- admin commands
- Back / Cancel
- inactivity timeout handling

Main files:
- `app/bot/handlers.py`
- `app/bot/keyboards.py`
- `app/bot/states.py`
- `app/i18n/*`

### 2) Runtime / worker layer
This layer uses a single shared Telethon session.
It resolves sources, watches active pairs, scans new messages, applies repost filters, and sends to targets.
It restores from Neon/Postgres after restart because pairs, recent duplicate state, and source registry live in the database.

Main files:
- `app/services/runtime.py`
- `app/services/repost_logic.py`
- `app/services/pair.py`
- `app/services/source_registry.py`
- `app/telegram/*`

## Important session rule

Use **one shared Telethon StringSession only**.
- End users never provide their own sessions.
- The admin puts the shared session into environment variables.
- Public sources are resolved and watched only.
- Private sources require invite links and may be joined by the shared session account.
- If an old private source is no longer used by any active pair anywhere in the system, the shared session may leave it.

## Source behavior

### Public source
- resolve and watch only
- do **not** join

### Private source
- invite link required
- join through the shared session
- track source reference count in the source registry

### Leave logic
When a pair is deleted or a source is edited:
- if the old source is still used by any other active pair, it is kept
- if no active pair needs it anymore and it had been joined privately, the shared session can leave it

## Features included

### User-facing
- OTP-based access control
- beginner-friendly tutorial/help
- ReplyKeyboard main menu
- inline button flows
- Add Pair
- Delete Pair
- Edit Source
- Edit Target
- Keyword management
- Ads management
- Status
- Check
- Forward Rule
- Post Rule
- Contact admin
- English + Myanmar localization
- Back / Cancel in all main flows
- inactivity timeout reset

### Admin commands
- `/otp [duration] [key]`
- `/info [id]`
- `/ban [id]`
- `/unban [id]`
- `/pair_limit [limit]`
- `/pair_limit [id] [limit]`
- `/noti [message]`
- `/list_active`
- `/list_expired`
- `/reset_user [id]`
- `/runtime_reload`
- `/source_debug`
- `/joined_sources`

## Beginner setup tutorial inside the bot

The bot explains:
- what the bot does
- what source means
- what target means
- that one shared watcher account is used
- why public sources are not joined
- why private sources need invite links
- how source leave logic works
- what pair numbers mean
- what scan amount means
- what ads mean
- what keyword modes mean
- what forward rule means
- what post rule means
- how check works
- how status works
- how Back and Cancel work
- common mistakes and fixes

## Exact repost logic kept from the old repo

### Post rule OFF
- repost all normal posts
- still obey forward rule, keyword rules, duplicate protection, and ads

### Post rule ON
- only video single posts or albums containing video are treated as main repost candidates
- if a single video post is allowed, the immediately previous post may be sent as preview
- if a video album is allowed, the immediately previous post or previous album may be sent as preview
- preview bypasses the video-only restriction, but still obeys:
  - forward rule
  - keyword rules
  - duplicate protection
- preview is not sent by itself if the main candidate is blocked

### Forward rule
- OFF = forwarded content is allowed
- ON = forwarded single posts, forwarded albums, and forwarded preview content are skipped

### Keywords
Each pair has:
- `off`
- `ban`
- `post`

Rules:
- multiple keywords supported
- comma-separated input
- case-insensitive matching
- normal posts, albums, and preview content all obey keyword logic

### Ads
- stored per pair
- multiple links supported
- appended to outgoing text or caption
- multiple ads are joined by newline consistently

### Duplicate protection
- recent sent IDs are stored in DB
- last processed ID is stored in DB
- protects normal posts, albums, preview reposts, and restart recovery

### Check / scan
- check starts from stored `last_processed_id`
- supports a single pair or all pairs
- scan amount supports numbers and `all`

### Queue behavior
- source-level lock prevents same-source collisions
- target-level lock reduces messy interleaving when multiple pairs send into the same target

## Database design

Neon/Postgres is the main source of truth.

Tables created automatically on startup:
- `users`
- `otp_keys`
- `global_settings`
- `sources`
- `pairs`
- `runtime_meta`

### Users
Stores:
- user id
- username / full name
- language
- activation status
- activated until
- ban state
- optional per-user pair limit
- restore-choice flag

### OTP keys
Stores:
- key hash
- duration code
- creation metadata
- redeemed user
- redeemed time
- activated until
- used flag

### Sources
Stores:
- normalized source identity
- public/private/id kind
- invite hash when needed
- whether shared session joined it
- active pair reference count
- chat id / title
- last verification info

### Pairs
Stores:
- user id
- pair number
- source / target
- scan count
- last processed id
- recent sent IDs
- forward rule
- post rule
- keyword mode + values
- ads
- active flag

## Folder guide

```text
app/
├─ bot/           # Telegram bot UI and FSM flow handling
├─ core/          # config, constants, logging, exceptions
├─ db/            # async DB connection, migrations, repositories
├─ domain/        # dataclasses / records
├─ i18n/          # localization strings and translator
├─ services/      # pair logic, source registry, runtime, repost rules, tutorials
├─ telegram/      # Telethon shared client, safe ops, entity resolving
└─ web/           # health endpoint
```

## Environment variables

Copy `.env.example` to `.env` and fill these values.

Required:
- `BOT_TOKEN`
- `API_ID`
- `API_HASH`
- `SESSION_STRING`
- `DATABASE_URL`
- `ADMIN_IDS`

Optional:
- `DEFAULT_PAIR_LIMIT`
- `DEFAULT_SCAN_COUNT`
- `POLL_INTERVAL_SECONDS`
- `HEALTH_PORT`
- `FLOW_TIMEOUT_MINUTES`
- `LANGUAGE_DEFAULT`
- `LOG_LEVEL`
- `DELAY_MIN_SECONDS`
- `DELAY_MAX_SECONDS`
- `RECENT_IDS_LIMIT`
- `LATEST_RECHECK_LIMIT`

## Local run guide

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill .env
python main.py
```

On startup the app:
1. loads env
2. runs DB migrations
3. starts the shared Telethon session
4. verifies authorization
5. starts the runtime loop
6. starts the health endpoint
7. starts bot polling

## Render deploy guide

`render.yaml` is included.

Basic flow:
1. Create a new Render web service.
2. Use this repo as the source.
3. Set the environment variables from `.env.example`.
4. Build command: `pip install -r requirements.txt`
5. Start command: `python main.py`
6. Health path: `/healthz`

## Neon setup guide

1. Create a Neon database.
2. Copy the connection string.
3. Put it into `DATABASE_URL`.
4. The app will auto-create the required tables on startup.

## Shared session setup guide

1. Log in to your Telegram user account through Telethon locally.
2. Generate a valid `StringSession`.
3. Put it into `SESSION_STRING`.
4. Make sure that session account can reach the sources and can send to targets that need posting.

## UptimeRobot note

If you use a free Render service and want fewer sleep gaps, point UptimeRobot to:
- `https://YOUR-RENDER-URL/healthz`

## Edge cases solved

### Access and OTP
1. Invalid OTP -> rejected
2. Used OTP -> rejected
3. Expired user -> blocked until new OTP
4. Banned user -> blocked with admin contact
5. Expired user with old data -> restore or fresh choice shown
6. Fresh start -> old active pairs archived, runtime cache rebuilt
7. Reuse old info -> pairs remain active and continue safely

### Flow safety
8. Buttons pressed out of order -> ignored unless current state matches
9. Text sent during button-only steps -> user is told to use buttons
10. Inactivity timeout -> state cleared after timeout window
11. `/start` during a flow -> state cleared and start flow restarts cleanly
12. Back -> returns to previous saved step prompt
13. Cancel -> exits full flow and returns to main menu
14. Language switch mid-flow -> language saved and current prompt can be re-shown in the new language

### Pair and source validation
15. Pair number already exists -> rejected
16. Pair limit exceeded -> rejected
17. Same source used more than 3 times per user -> rejected
18. Public source cannot be resolved -> create/edit fails with Telethon resolution error
19. Invalid private invite -> create/edit fails
20. Shared session join failure -> create/edit fails
21. Public source never joins -> only resolved
22. Private source joins only when needed -> invite import path only
23. Old source still used elsewhere -> not left
24. Old source unused after delete/edit -> safe leave attempted

### Runtime and repost safety
25. Duplicate repost after restart -> protected by stored `recent_sent_ids` and `last_processed_id`
26. Keyword updates while runtime is active -> runtime reads latest saved pair data on next cycle
27. Ads updates while runtime is active -> next send uses latest pair config
28. Pair deletion while runtime watches -> pair becomes inactive and source cleanup runs
29. Check while runtime already processing -> source and target locks serialize work
30. Preview logic never bypasses forward or keyword filters
31. Preview is never sent by itself when main content is blocked
32. Album and single reposts both obey duplicate protection
33. FloodWait -> handled by safe Telethon wrappers that sleep and retry
34. Session disconnect warning -> visible in status as runtime warning
35. Render restart -> runtime rebuilds from DB on startup because active pairs are stored in DB
36. Neon restart / reconnect -> new async connections are opened per repository operation

## Troubleshooting

### Nothing is posting
Check these first:
- source is valid
- target is valid
- shared session can send to target
- forward rule is not blocking forwarded content
- keyword mode is not filtering the post
- post rule is not excluding non-video content

### Source cannot be resolved
- verify the public username or public link
- verify the private invite link
- verify the shared session still has access

### Target cannot be posted to
- the shared session may need to be member or admin there
- the target may be wrong or unreachable

### OTP problems
- make sure the key exists
- make sure it was not already redeemed
- use `/otp [duration] [key]` again from an admin account if you need a new one

### Access expired
- run `/start`
- send a new OTP
- choose restore or fresh start

## Notes on verification

The code is written to be deployable and compile-clean, but live Telegram behavior still depends on your real credentials, channel permissions, and network environment.
