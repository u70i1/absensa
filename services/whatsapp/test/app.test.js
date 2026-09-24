"use strict";

const assert = require("node:assert/strict");
const { after, before, test } = require("node:test");
const { createApp, normalizePhone } = require("../src/app");
const { GatewayError } = require("../src/gateway");

const token = "a-test-token-with-at-least-32-characters";
const calls = [];
const gateway = {
  snapshot: () => ({ state: "disconnected", phone: null, qr_available: false }),
  connect: () => ({ state: "starting", phone: null, qr_available: false }),
  qr: () => ({ state: "qr", phone: null, qr_available: true, qr_data_url: "data:image/png;base64,Y29kZQ==" }),
  sendMessage: async (phone, message) => {
    calls.push({ phone, message });
    if (phone === "628999999999") throw new GatewayError("number_not_registered", 422);
    return { sent: true };
  },
};
let server;
let baseUrl;

before(async () => {
  server = createApp({ gateway, token }).listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});
after(() => new Promise((resolve) => server.close(resolve)));

function request(path, options = {}) {
  return fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...options.headers },
  });
}

test("bridge routes require the shared token", async () => {
  assert.throws(() => createApp({ gateway, token: "replace-with-this-placeholder-value" }));
  assert.equal((await fetch(`${baseUrl}/api/status`)).status, 401);
  assert.equal((await request("/api/status", { headers: { Authorization: "Bearer wrong" } })).status, 401);
  assert.equal((await fetch(`${baseUrl}/health`)).status, 200);
});

test("status, connect, and QR routes provide the admin contract", async () => {
  const status = await (await request("/api/status")).json();
  assert.equal(status.state, "disconnected");
  assert.equal((await request("/api/connect", { method: "POST" })).status, 202);
  const qr = await (await request("/api/qr")).json();
  assert.equal(qr.qr_data_url, "data:image/png;base64,Y29kZQ==");
});

test("phone and message validation on the transport endpoint", async () => {
  assert.equal(normalizePhone("+62 811-1111-111"), "628111111111");
  assert.equal(normalizePhone("javascript:alert(1)"), null);
  const send = (phone, message) => request("/api/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, message }),
  });
  assert.equal((await send("abc", "Halo")).status, 422);
  assert.equal((await send("628111111111", "")).status, 422);
  assert.equal((await send("628999999999", "Halo")).status, 422);
  assert.equal((await send("+62 811-1111-111", "Halo {{already rendered}}")).status, 200);
  assert.deepEqual(calls, [{ phone: "628999999999", message: "Halo" }, { phone: "628111111111", message: "Halo {{already rendered}}" }]);
});
