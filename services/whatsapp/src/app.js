"use strict";

const { timingSafeEqual } = require("node:crypto");
const express = require("express");
const { GatewayError } = require("./gateway");

function normalizePhone(value) {
  if (typeof value !== "string") return null;
  const compact = value.trim().replace(/[\s()-]/g, "");
  if (!/^\+?[1-9]\d{7,14}$/.test(compact)) return null;
  return compact.replace(/^\+/, "");
}

function createApp({ gateway, token }) {
  if (!token || token.length < 32 || token.startsWith("replace-with-")) {
    throw new Error("BRIDGE_API_TOKEN must be a generated secret with at least 32 characters");
  }
  const app = express();
  const expectedBytes = Buffer.from(token);
  app.disable("x-powered-by");
  app.use(express.json({ limit: "8kb" }));

  app.get("/health", (_request, response) => response.json({ ok: true }));
  app.use("/api", (request, response, next) => {
    const provided = request.get("authorization")?.replace(/^Bearer /, "") || "";
    const providedBytes = Buffer.from(provided);
    if (providedBytes.length !== expectedBytes.length || !timingSafeEqual(providedBytes, expectedBytes)) {
      return response.status(401).json({ error: "unauthorized" });
    }
    next();
  });

  app.get("/api/status", (_request, response) => response.json(gateway.snapshot()));
  app.post("/api/connect", (_request, response) => {
    try {
      return response.status(202).json(gateway.connect());
    } catch {
      return response.status(503).json({ error: "initialization_failed" });
    }
  });
  app.get("/api/qr", (_request, response) => response.json(gateway.qr()));
  app.post("/api/messages", async (request, response) => {
    const phone = normalizePhone(request.body?.phone);
    if (!phone) return response.status(422).json({ error: "invalid_phone" });
    const message = request.body?.message;
    if (typeof message !== "string" || !message.trim() || message.length > 4000) {
      return response.status(422).json({ error: "invalid_message" });
    }
    try {
      return response.json(await gateway.sendMessage(phone, message));
    } catch (error) {
      if (error instanceof GatewayError) {
        return response.status(error.status).json({ error: error.code });
      }
      return response.status(502).json({ error: "send_failed" });
    }
  });
  app.use((error, _request, response, _next) => {
    if (error instanceof SyntaxError && "body" in error) {
      return response.status(400).json({ error: "invalid_json" });
    }
    return response.status(500).json({ error: "internal_error" });
  });
  return app;
}

module.exports = { createApp, normalizePhone };
