# Cloudflare tunnel secret

Create `secrets/cf_token.txt` with the tunnel token from the Cloudflare dashboard
(or `cloudflared tunnel token <tunnel-id>`).

The file must be readable by the `cloudflared` container, which runs as uid
65532. On Linux:

```bash
chmod 755 secrets
chmod 644 secrets/cf_token.txt
```

The file is gitignored. Never put the token in `environment:` or in a committed
file.
