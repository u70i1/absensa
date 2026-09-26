# Run Absensa locally

Absensa has four running parts: PostgreSQL, FastAPI, the WhatsApp bridge, and
the notification scheduler. You need Python, Node.js 18+, Docker, and Chromium.
Run commands from the directories shown so each service reads its own `.env`
and keeps its local files in the expected place.

## One-time setup

From the repository root, start PostgreSQL:

```bash
docker compose up -d db
```

The default database is on `localhost:5433`. Set up FastAPI from `web/`.
After copying the example, check `DATABASE_URL` and `TIMEZONE` in `web/.env`
before running migrations. Keep `TEST_DATABASE_URL` pointed at a different
database if you run the test suite.

```bash
cd web
cp -n .env.example .env
# Check the database URL and timezone in .env before the next commands.
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.create_admin admin
```

The admin command prompts for a password. Existing `.env` files are preserved.

Install Chromium, then set up the bridge. The next `cd` assumes you are still
in `web/`:

```bash
cd ../services/whatsapp
cp -n .env.example .env
PUPPETEER_SKIP_DOWNLOAD=1 npm ci
```

Set `CHROME_PATH` in the bridge `.env` to the Chromium executable.
Generate one random token with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`. Put the same
token in `BRIDGE_API_TOKEN` in `services/whatsapp/.env` and
`WHATSAPP_BRIDGE_TOKEN` in `web/.env`. The default bridge address is
`http://127.0.0.1:3001`. Set `CHROME_NO_SANDBOX=true` only if your Chromium
environment requires it.

## Start the services

Keep three terminals open, each in the directory shown:

| Terminal | Directory | Command |
| --- | --- | --- |
| FastAPI | `web/` | `.venv/bin/uvicorn app.main:app --reload` |
| WhatsApp bridge | `services/whatsapp/` | `npm start` |
| Notification scheduler | `web/` | `.venv/bin/python -m app.jobs.whatsapp_notifications` |

PostgreSQL stays running through Docker. The scheduler is a **separate process**;
the FastAPI server and `/admin/whatsapp/daily` do not start it. Keep exactly
one scheduler running. It checks the schedule every 30 seconds. For a lasting
deployment, supervise all three processes so they restart if they exit; leave
`--reload` off FastAPI outside development.

Open `http://localhost:8000/admin` and sign in. Under **Akses & Perangkat**,
create a TrustedDevice and an Operator if you need the scanning interface.
Their login sequence starts at `/trusteddevice/login`. Under **WhatsApp
Gateway**, request a QR code and link the WhatsApp account. Enable automatic
notifications, choose the send time, and set the minimum attendance. Students
need guardian phone numbers to receive messages; students already present are
excluded. The page's **Test** action sends a real message to the number you
enter, regardless of the automatic schedule.

## If sending fails

Check the **bridge terminal** first. A successful `/api/status` response means
the account appears connected; it does not prove that `/api/messages` succeeded.
The bridge logs whether recipient lookup or sending failed, with phone numbers
and message text redacted. A `502` pauses the day's batch with **Layanan WhatsApp
gagal** (`needs_attention`). Review the bridge error and delivery outcome before using
**Lanjutkan pengiriman**: previously claimed students, including uncertain sends,
are skipped to avoid duplicate WhatsApp messages. The dashboard reports partial
completion if any deliveries remain failed or uncertain.

Keep `services/whatsapp/.wwebjs_auth/` and `web/photos/` persistent if their
contents should survive restarts.
