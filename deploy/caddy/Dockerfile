# Official container packaging lags the Caddy source release; replace its binary
# with the explicitly versioned security release below (never build @latest).
FROM caddy:2.11.4-builder AS builder
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    xcaddy build v2.11.6 --with github.com/caddy-dns/cloudflare@v0.2.4
FROM caddy:2.11.4
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
