# Security and privacy

**English** · [繁體中文](zh-TW/security.md) · [简体中文](zh-CN/security.md)

## Security and privacy

- Complete first-run setup before exposing the service. While no account exists,
  `/api/v1/auth/setup` is public by design; do not leave a fresh instance
  reachable through a tunnel before the root account is created.
- One root plus normal accounts protect the archive. Passwords are hashed with
  Argon2; session tokens are stored only as SHA-256 hashes in `user_session`.
  The cookie is HttpOnly, SameSite=Lax, and Secure when
  `APSOR_COOKIE_SECURE=true`. A temporary password is returned once, never
  logged or cached, and the account must change it before loading content.
- Every private row carries `user_id`; composite foreign keys keep lineage
  inside one account, and PostgreSQL forced row-level security on `apsor_app`
  denies cross-account reads and writes even if a service filter is missing.
  Root-only route guards protect accounts and global settings, but root is not a
  data superuser and cannot read another account's archive through normal API
  queries. Root password reset and explicit impersonation are deliberate
  trusted-recovery capabilities that can transfer sign-in access to the target
  account; stopping impersonation requires the root password, deletes that
  session, and issues a fresh root session. Treat root as the highest-trust
  credential and do not model RLS as protection against a malicious root.
- **Companion administration is a documented exception.** Under
  `/api/v1/admin/companions`, a root request also sets the transaction-local
  `app.admin_scope = 'companion'`. Database policies then let root read and
  manage companion rows across accounts: the companion choice and policy,
  story progress (bonds and told memories), root's persona and lore overrides,
  life-story jobs, and the **full text of generated life stories**, which are
  written from an account's own memories. The scope never reaches the archive
  itself (`file`, `memory`, `chunk`, conversations), is refused for any role but
  root, and does not apply in an impersonated session. Every full-text read of
  a life story and every per-account companion change is appended to
  `companion_admin_access_log` (root can insert and read it; nothing can update
  or delete it), and story listings never carry the text. The account's
  Companion page states that the administrator can read these stories.
- **RLS is an application boundary, not a host boundary.** The deployment login
  is a PostgreSQL superuser used for migrations and maintenance; the app
  switches to `apsor_app` for request transactions. Any local OS user, any
  container on the database/cache network, or anyone who can read
  `.secrets/`/`.env` can bypass the API and RLS. Keep the host trusted, keep the
  database and cache bound to localhost or an internal network, use distinct
  host accounts, set a strong database/cache password for any shared host, and
  rotate credentials after exposure. A future hardening step is a dedicated
  non-superuser runtime login plus a separate maintenance credential.
- The production Compose file publishes no host port; Cloudflare Tunnel reaches
  Caddy, and Caddy reaches the API. Login throttling is in-memory and therefore
  single-process; run one API process, or move the throttle to Valkey before
  scaling out.
- Paths reject traversal segments, backslashes, control characters, and
  over-long values. Uploads are capped at 10 MB and restricted to an extension
  allowlist.
- HTML from files and memories is rendered as text through React. Agent Markdown
  uses `skipHtml`; DOCX previews run in a script-disabled sandbox and PPTX slides
  render to a local canvas. The UI never uses `dangerouslySetInnerHTML`.
- The DeepSeek key lives in `.secrets/deepseek.env` or the environment. It is
  never logged, returned, or committed. Keys saved from the Settings page are
  encrypted in PostgreSQL and returned only as a four-character hint.
- Object-store credentials live in the gitignored `.secrets/r2.env` or
  `.secrets/s3.env` (and, for the bundled RustFS, Docker secret files under
  `secrets/`), are mounted read-only, and never become container environment
  variables. Buckets are private, with no presigned or public URLs.
- AI calls happen for summaries and agent turns. If the provider fails, the API
  returns a stable error instead of inventing an answer.
