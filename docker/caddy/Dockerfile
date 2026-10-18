FROM caddy:2.11.4-alpine

RUN apk add --no-cache libcap tzdata \
    && addgroup -g 1000 -S caddy \
    && adduser -u 1000 -S -D -G caddy caddy \
    && setcap cap_net_bind_service=+ep /usr/bin/caddy \
    && mkdir -p /var/log/caddy /config /data \
    && chown -R caddy:caddy /var/log/caddy /config /data

COPY Caddyfile /etc/caddy/Caddyfile
USER caddy
