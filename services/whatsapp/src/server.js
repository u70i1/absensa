"use strict";

require("dotenv").config();

const { existsSync } = require("node:fs");
const path = require("node:path");
const QRCode = require("qrcode");
const { Client, LocalAuth } = require("whatsapp-web.js");
const { createApp } = require("./app");
const { createGateway } = require("./gateway");

const host = process.env.BRIDGE_HOST || "127.0.0.1";
const port = Number(process.env.BRIDGE_PORT || 3001);
const authDir = path.resolve(process.env.WHATSAPP_AUTH_DIR || ".wwebjs_auth");
const noSandbox = process.env.CHROME_NO_SANDBOX === "true";
const QR_IMAGE_SIZE = 320; // Clear enough to scan in the admin dashboard card.

const gateway = createGateway({
  createClient: () => new Client({
    authStrategy: new LocalAuth({ dataPath: authDir }),
    puppeteer: {
      headless: true,
      ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
      args: noSandbox ? ["--no-sandbox", "--disable-setuid-sandbox"] : [],
    },
  }),
  encodeQr: (value) => QRCode.toDataURL(value, { margin: 2, width: QR_IMAGE_SIZE }),
});

const app = createApp({ gateway, token: process.env.BRIDGE_API_TOKEN });
app.listen(port, host, () => {
  console.log(`Absensa WhatsApp bridge listening on http://${host}:${port}`);
  // A saved LocalAuth profile should reconnect after a service restart.
  if (existsSync(authDir)) gateway.connect();
});
