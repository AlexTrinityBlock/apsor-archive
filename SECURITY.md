# Security Policy

Apsor Archive is a self-hosted, single-deployment archive. This policy covers
the threat model, the supported release, vulnerability reporting, and operator
responsibilities.

## Threat model

Apsor Archive runs one root account and any number of normal accounts, each
with a private archive.

Account isolation has two layers:

- every private row carries `user_id`, and parent/child links use composite
  `(id, user_id)` foreign keys;
- request transactions and scoped worker jobs run as the non-login `apsor_app`
  role with transaction-local `app.user_id` and `app.user_role`, and forced
  PostgreSQL row-level security is default-deny on private tables.

This is an application boundary, not a host boundary. The operator is trusted.
The deployment login is a PostgreSQL superuser used for migrations and
maintenance, and anyone with shell access, database or cache credentials,
`.env`, `.secrets/`, or the data directory can bypass the API and RLS.

Root is the highest-trust credential. Root manages accounts, resets passwords,
and can start a marked impersonation session for a normal account. Those
capabilities can transfer sign-in access to the target, so root can read that
archive even though ordinary root API queries remain owner-scoped. RLS is not
protection against a malicious root or a compromised host.

Other boundaries:

- Passwords use Argon2. Session tokens are stored as SHA-256 hashes; the
  cookie is HttpOnly and SameSite=Lax, and Secure when
  `APSOR_COOKIE_SECURE=true`.
- `/api/v1/auth/setup` is public while no account exists. Create root before
  exposing the instance.
- Login throttling is in memory and per process. Run one API process unless
  throttling moves to a shared store.
- When configured, remote chat, embedding, search, and fetch providers receive
  the data those operations require.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.0 | Yes |

`0.1.0` is the only supported release. There are no maintained release
branches and no backports. Fixes land on the default branch and in the next
release.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: open the **Security** tab and
choose **Report a vulnerability**. Do not open a public issue, pull request, or
discussion with exploit details. The repository does not publish a security
email address.

Include the affected version or commit, the deployment shape (local Compose,
Cloudflare Tunnel, or bare metal), reproduction steps and required
configuration, the impact, and whether you want public credit.

We aim to acknowledge a report within seven days. Acknowledgement is not a fix
commitment; the timeline depends on severity and complexity. We will coordinate
disclosure after a fix is available.

## Operator responsibilities

- Keep `.secrets/` and `secrets/` out of version control; `secrets/README.md`
  is the only tracked file in those directories. Rotate exposed credentials.
- Provider keys saved in Settings are Fernet-encrypted using
  `APSOR_SECRET_KEY` or `data/.secret_key` (mode 0600). Never log or return
  them in plaintext, or place them in a URL. Keys in `.secrets/*.env` are
  plaintext files and need strict permissions.
- Back up PostgreSQL and `data/.secret_key` separately; without the key,
  encrypted provider credentials cannot be recovered. If R2 is used, include
  the bucket backup and `.secrets/r2.env` in the recovery set.
- Keep the tunnel token in `secrets/cf_token.txt` and R2 credentials in
  `.secrets/r2.env`, consumed as files. Do not put either in container
  `environment:` entries.
- Terminate TLS at the Cloudflare Tunnel or a reverse proxy. Set
  `APSOR_COOKIE_SECURE=true` for HTTPS.
- Do not expose PostgreSQL or Valkey beyond loopback or an internal network.
  The normal Compose file binds both to `127.0.0.1`; the tunnel file publishes
  no host port.
- Keep the host, images, and database login trusted; RLS does not constrain a
  host administrator or the owner login.

## Out of scope

- issues requiring a malicious host administrator or OS, database, cache, or
  secret-file access;
- issues requiring a compromised deployment, modified image, or stolen
  session or credential;
- issues caused by a deliberately misconfigured reverse proxy, TLS terminator,
  or access policy;
- denial of service by resource exhaustion on a self-hosted instance;
- a leaked secret that was never committed. Treat that as an operational
  incident: rotate the secret and review access logs.
