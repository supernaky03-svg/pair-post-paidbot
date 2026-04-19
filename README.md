# Telegram multi-user repost userbot

This repo upgrades the old `telegram-userbot` into a multi-user production-ready version while keeping the old repost workflow as much as possible.

## What stayed from the old repo

The repost core still keeps the old behavior pattern:

- Telethon user account does the real reading/scanning/reposting
- post rule still means "video-focused reposting"
- forward rule still skips forwarded posts
- caption/text cleanup still removes links and appends ads
- previous preview text before video is still preserved
- scan logic still uses `last_processed_id`, initial scan count, and latest recheck
- duplicate prevention still uses `recent_sent_ids`

## What changed

- Telegram bot token now handles all user interaction
- many users can use the same system safely
- each user has isolated pairs and isolated database channel
- Neon/Postgres stores permanent metadata and pair state
- OTP licensing system is enforced before use
- admin commands manage bans, pair limits, broadcast, and OTP creation
- same-source duplicates are limited to 3 pairs and processed through a shared source queue

## Folder structure

```text
app/
  bot/
    handlers/
      admin.py
      user.py
    router.py
  core/
    config.py
    logging.py
    runtime.py
  db/
    database.py
    repositories.py
    schema.sql
  services/
    access.py
    db_channel.py
    entity.py
    health.py
    queueing.py
    reposting.py
    user_actions.py
    worker.py
  utils/
    filters.py
    parsing.py
    telethon.py
    text.py
  keyboards.py
  localization.py
  models.py
  states.py
  main.py
main.py
requirements.txt
.env.example
render.yaml
```

## Database schema

The SQL schema is in `app/db/schema.sql`.

Main tables:

- `users`
- `otp_keys`
- `user_pairs`
- `app_settings`
- `admin_logs`

## Required environment variables

Use `.env.example` as the template.

Important notes:

- `TELETHON_SESSION_STRING` must already be authorized before deployment.
- `DATABASE_URL` should be your Neon connection string.
- `ADMIN_IDS` is a comma-separated list of Telegram user IDs allowed to use admin commands.

## Render deployment

1. Create a Neon database and copy the connection string.
2. Generate a Telethon session string locally using your Telegram user account.
3. Push this project to GitHub.
4. Create a Render web service.
5. Set the start command to `python main.py`.
6. Add all environment variables from `.env.example`.
7. Set Render health check path to `/health`.
8. Point UptimeRobot to `/health` or `/` if you want extra keep-awake pings.

## OTP system

Admin command example:

```text
/otp 1m somekey
```

Supported duration units:

- `d` = day
- `w` = week
- `m` = month
- `y` = year

OTP behavior:

- OTP does not expire before first use
- after use it becomes permanently invalid
- redeeming it grants access until `access_expires_at`

## Same-source queue design

The old repost logic can fail if the same source is reused too many times in parallel. To solve this, the new version introduces a shared queue per resolved source chat:

- every source gets its own queue key
- all repost jobs for that source are serialized
- up to 3 pairs can safely share the same source
- scan jobs and live event jobs both go through the same queue

Result: duplicate same-source pairs do not send concurrently into Telegram and are much less likely to hit timing collisions.

## Expired user restore vs reset

When an expired user redeems a new OTP:

### Reuse previous info
- keeps old pair data
- keeps old database channel
- continues with previous configuration

### Start from beginning
- clears old pairs from Neon
- clears the saved database channel reference
- increments `reset_version`
- asks for database channel again
- writes a fresh snapshot after reset
- old channel history is logically ignored because future snapshots are attached to the new reset version

## Localization

Major user-facing texts support:

- English
- Myanmar

The language can be changed from the `Language` menu.

## Notes about database channel usage

Neon stores the durable operational data.  
The per-user private channel is additionally used as an isolated state mirror/snapshot log for that specific user, so their pair/settings history is never mixed with another user's data.

## Old repo compatibility

This upgrade intentionally keeps the old Telethon repost style instead of replacing it with a completely new pipeline. Most refactoring is around:

- multi-user isolation
- bot menu / FSM UX
- OTP and access control
- Neon persistence
- source queueing
- database channel verification and snapshot mirroring
