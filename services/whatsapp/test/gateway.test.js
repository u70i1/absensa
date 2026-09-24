"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { test } = require("node:test");
const { createGateway, GatewayError, TEST_MESSAGE } = require("../src/gateway");

class FakeClient extends EventEmitter {
  constructor() {
    super();
    this.info = { wid: { user: "6281234567890" } };
    this.initializations = 0;
    this.sent = [];
  }

  async initialize() { this.initializations += 1; }
  async destroy() {}
  async getNumberId(number) { return number === "628111111111" ? { _serialized: `${number}@c.us` } : null; }
  async sendMessage(to, message) { this.sent.push({ to, message }); }
}

test("connection is idempotent, exposes a QR, and reports the linked phone", async () => {
  const client = new FakeClient();
  const gateway = createGateway({ createClient: () => client, encodeQr: async (value) => `data:image/png;base64,${value}` });
  assert.equal(gateway.snapshot().state, "disconnected");
  assert.equal(gateway.connect().state, "starting");
  gateway.connect();
  await new Promise(setImmediate);
  assert.equal(client.initializations, 1);

  client.emit("qr", "Y29kZQ==");
  await new Promise(setImmediate);
  assert.equal(gateway.qr().qr_data_url, "data:image/png;base64,Y29kZQ==");
  client.emit("authenticated");
  assert.equal(gateway.qr().qr_data_url, null);
  client.emit("ready");
  assert.deepEqual(gateway.snapshot(), { state: "connected", phone: "6281234567890", qr_available: false });
});

test("test message uses the registered WhatsApp ID and fixed text", async () => {
  const client = new FakeClient();
  const gateway = createGateway({ createClient: () => client, encodeQr: async () => "unused" });
  await assert.rejects(gateway.sendTestMessage("628111111111"), { code: "not_connected", status: 409 });
  gateway.connect();
  client.emit("ready");
  await assert.rejects(gateway.sendTestMessage("628999999999"), { code: "number_not_registered", status: 422 });
  assert.deepEqual(await gateway.sendTestMessage("628111111111"), { sent: true });
  assert.deepEqual(client.sent, [{ to: "628111111111@c.us", message: TEST_MESSAGE }]);
  client.emit("disconnected");
  assert.equal(gateway.snapshot().state, "disconnected");
  assert.ok(GatewayError);
});

test("old QR generation cannot replace a newer QR or connected state", async () => {
  const client = new FakeClient();
  const resolves = [];
  const gateway = createGateway({ createClient: () => client, encodeQr: () => new Promise((resolve) => resolves.push(resolve)) });
  gateway.connect();
  client.emit("qr", "old");
  client.emit("qr", "new");
  resolves[1]("data:image/png;base64,bmV3");
  resolves[0]("data:image/png;base64,b2xk");
  await new Promise(setImmediate);
  assert.equal(gateway.qr().qr_data_url, "data:image/png;base64,bmV3");
  client.emit("ready");
  assert.equal(gateway.qr().qr_data_url, null);
});
