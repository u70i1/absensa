FROM node:26-bookworm-slim
ENV NODE_ENV=production PUPPETEER_SKIP_DOWNLOAD=true \
    CHROME_PATH=/usr/bin/chromium BRIDGE_HOST=0.0.0.0 \
    WHATSAPP_AUTH_DIR=/app/.wwebjs_auth
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium ca-certificates fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force \
    && mkdir .wwebjs_auth .wwebjs_cache \
    && chown node:node .wwebjs_auth .wwebjs_cache
COPY src ./src
USER node
EXPOSE 3001
CMD ["node", "src/server.js"]
