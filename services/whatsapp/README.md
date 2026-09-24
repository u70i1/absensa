# WhatsApp bridge

This Express service owns the `whatsapp-web.js` client. FastAPI is the only
caller: administrators use `/admin/whatsapp`, and the browser never calls the
bridge directly. The bridge listens on `127.0.0.1:3001` by default and requires
a shared bearer token on all `/api` routes.

1. Copy `.env.example` to `.env`. Generate a random token with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`, then put it in
   `BRIDGE_API_TOKEN`. Put the same value in `WHATSAPP_BRIDGE_TOKEN` in
   `web/.env`. Set `WHATSAPP_BRIDGE_URL` there if the bridge uses another host or
   port. Keep both `.env` files out of version control.
2. Install Chromium, set `CHROME_PATH` to its executable, then run
   `PUPPETEER_SKIP_DOWNLOAD=1 npm ci` in this directory. This uses the system
   browser instead of Puppeteer's browser downloader. On systems that require
   Chromium without its sandbox, set `CHROME_NO_SANDBOX=true` for this
   dedicated service.
3. Run `npm start` here and the FastAPI application from `web/`. Open the
   **WhatsApp Gateway** tab as an admin, request a QR code, and scan it from
   WhatsApp's **Linked devices** menu. The dashboard refreshes the pairing
   status automatically until connected.

The `LocalAuth` profile lives in `.wwebjs_auth/` by default and is ignored by
Git. Keep that directory private and persistent across restarts. The service
reconnects automatically on startup when a saved profile exists. FastAPI owns
notification settings, schedule, student selection, message rendering, and
rate limiting; this bridge receives only a phone number and final message.

The bridge API consists of `GET /health`, authenticated `GET /api/status`,
`POST /api/connect`, `GET /api/qr`, and `POST /api/messages` with JSON
`{"phone":"6281234567890","message":"Final text"}`. Run `npm test`
for the bridge's mocked client and HTTP contract tests. A real QR scan and
message delivery still require a WhatsApp account and running Chromium.

`whatsapp-web.js` uses the unofficial WhatsApp Web client; consult its
[official project guide](https://wwebjs.dev/guide/) before using this beyond
the prototype.
