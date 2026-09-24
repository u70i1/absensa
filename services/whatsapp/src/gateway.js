"use strict";

const TEST_MESSAGE = "hi from absensa";

class GatewayError extends Error {
  constructor(code, status) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

function createGateway({ createClient, encodeQr }) {
  let client = null;
  let state = "disconnected";
  let phone = null;
  let qrDataUrl = null;
  let qrRevision = 0;

  function snapshot() {
    return { state, phone, qr_available: Boolean(qrDataUrl) };
  }

  function reset(instance, nextState) {
    if (client !== instance) return;
    client = null;
    state = nextState;
    phone = null;
    qrDataUrl = null;
    qrRevision += 1;
    Promise.resolve().then(() => instance.destroy()).catch(() => {});
  }

  function connect() {
    if (client) return snapshot();

    const instance = createClient();
    client = instance;
    state = "starting";
    phone = null;
    qrDataUrl = null;
    qrRevision += 1;

    instance.on("qr", async (rawQr) => {
      const revision = ++qrRevision;
      try {
        const image = await encodeQr(rawQr);
        if (client !== instance || revision !== qrRevision || state === "connected") return;
        qrDataUrl = image;
        state = "qr";
      } catch {
        reset(instance, "error");
      }
    });
    instance.on("authenticated", () => {
      if (client !== instance) return;
      state = "starting";
      qrDataUrl = null;
      qrRevision += 1;
    });
    instance.on("ready", () => {
      if (client !== instance) return;
      phone = instance.info?.wid?.user || null;
      qrDataUrl = null;
      qrRevision += 1;
      state = "connected";
    });
    instance.on("auth_failure", () => reset(instance, "error"));
    instance.on("disconnected", () => reset(instance, "disconnected"));

    // Initialization opens Chromium and can take time. HTTP requests must not wait for it.
    Promise.resolve().then(() => instance.initialize()).catch(() => reset(instance, "error"));
    return snapshot();
  }

  async function sendTestMessage(recipient) {
    if (state !== "connected" || !client) {
      throw new GatewayError("not_connected", 409);
    }
    const registered = await client.getNumberId(recipient);
    if (!registered?._serialized) {
      throw new GatewayError("number_not_registered", 422);
    }
    await client.sendMessage(registered._serialized, TEST_MESSAGE);
    return { sent: true };
  }

  return {
    snapshot,
    connect,
    qr: () => ({ ...snapshot(), qr_data_url: qrDataUrl }),
    sendTestMessage,
  };
}

module.exports = { createGateway, GatewayError, TEST_MESSAGE };
