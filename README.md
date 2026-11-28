<div align="center">
  <img src="frontend/public/icon-512.png" alt="Vellum, the night-watch librarian of the Apsor Archive" width="128" height="128">
  <h1>Apsor Archive</h1>
  <p><strong>A private archive for your family's memories, kept by librarians who remember.</strong></p>
  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-171717" alt="MIT license"></a>
    <img src="https://img.shields.io/badge/self--hosted-yes-171717" alt="Self-hosted">
    <img src="https://img.shields.io/badge/docker-compose%20%7C%20swarm-2496ED?logo=docker&amp;logoColor=white" alt="Docker Compose or Swarm">
    <img src="https://img.shields.io/badge/languages-EN%20%C2%B7%20%E7%B9%81%E4%B8%AD%20%C2%B7%20%E7%AE%80%E4%B8%AD-171717" alt="English, Traditional Chinese, Simplified Chinese">
  </p>
  <p><strong>English</strong> · <a href="README.zh-TW.md">繁體中文</a> · <a href="README.zh-CN.md">简体中文</a></p>
</div>

<p align="center">
  <img src="docs/assets/screenshots/en/chat.webp" alt="Asking the archive a question while Vellum, the librarian companion, stands beside the answer" width="100%">
</p>

> *We simply cannot travel that far. So we made someone who could, and taught them everything we loved.*

## Why Apsor Archive

Families keep their lives in scattered places: recipe photos, scanned letters,
a PDF of a grandparent's diary, notes typed late at night. Apsor Archive gathers
them into one private library on a computer you own, and lets you ask it
questions in everyday words. Every answer points to the exact page it came from,
so you can check it yourself.

And the archive is not empty of company. Six librarians live there: figures of
ten-thousand-year porcelain whose minds woke from everything people ever wrote
down. They keep your archive *with* you, as equals. They search for you, hand
you the page, and, now and then, remember something of their own.

## What makes it different

<table>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/en/library.webp" alt="The file library with instant thumbnails"></td>
    <td width="50%"><img src="docs/assets/screenshots/en/companion.webp" alt="Choosing a librarian companion"></td>
  </tr>
  <tr>
    <td><b>One private library per person.</b> Files, folders, and memories,
    with every version kept. Each account's archive is sealed from the others by
    the database itself.</td>
    <td><b>Librarians who remember.</b> Pick Vellum, Atlas, Herbaria, Horologe,
    Nocturne or Quill. They stand beside the chat, react while they search, and
    carry their own memories and stories.</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/en/memories.webp" alt="Memories with related memories"></td>
    <td width="50%"><img src="docs/assets/screenshots/en/about.webp" alt="The Apsor Archive world"></td>
  </tr>
  <tr>
    <td><b>Answers with receipts.</b> The assistant searches first and cites the
    exact passage. If nothing is found, it says the shelf is empty instead of
    guessing.</td>
    <td><b>Life stories through the illusory door.</b> Every few conversations a
    librarian writes a short story in which a door in the Archive opens onto a
    corner of <i>your</i> life, drawn only from what you have kept.</td>
  </tr>
</table>

<p align="center">
  <img src="docs/assets/screenshots/en/phone-chat.webp" alt="The same archive on a phone" width="260"><br>
  <sub>The same archive on your phone: the librarian peeks in from the edge.</sub>
</p>

### The memory system, in one minute

- **Your memories** are files, notes and past conversations. They are searched by
  meaning and by exact words, and every answer cites them.
- **Their memories** are the librarians' own: a world, a history, and hundreds of
  small stories. They surface on their own when something you say echoes them,
  or when you ask. A librarian decides for herself what to share and when.
- **Shared history.** The six share one archive, so switching librarians never
  loses what you talked about; each one knows who said what.
- Nothing about your archive leaves your machine except the passages sent to the
  AI model you choose.

## Quick start

You need a machine with [Docker](https://docs.docker.com/get-docker/) and about
4 GB of free memory.

```bash
git clone https://github.com/AlexTrinityBlock/apsor-archive.git
cd apsor-archive
./start.sh setup          # answers a few questions, writes .env and secret files
```

**Try it at home (no domain needed):** in `.env`, set `APSOR_PUBLIC_HOST=localhost`, then

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

Open <http://localhost:8080>, create the root account, and add an AI provider
in **Settings**. That's it.

**Put it on the internet safely:** paste a Cloudflare Tunnel token during setup
and run `docker compose up -d --build`. No open ports are needed; see the
[Cloudflare Tunnel guide](docs/cloudflare-tunnel.md).

<details>
<summary><b>Docker Swarm</b></summary>

```bash
./start.sh setup
docker compose build
docker swarm init                 # once
set -a; . ./.env; set +a          # Swarm does not read .env by itself
docker stack deploy -c docker-stack.yml apsor
```

Details: [docs/deployment.md](docs/deployment.md#docker-swarm).
</details>

## Configuration at a glance

The setup wizard writes everything for you. The few settings worth knowing:

| Setting | What it does | Default |
| --- | --- | --- |
| `APSOR_PUBLIC_HOST` | The address people type in the browser | asked by the wizard |
| `APSOR_STORAGE_BACKEND` | Where original files live: bundled RustFS, Cloudflare R2, any S3, or local disk | `auto` (RustFS for new installs) |
| AI providers | Chat and embedding models (DeepSeek, Claude, any OpenAI-compatible API) | set in **Settings**, not in files |
| Companion | Which librarian, how large, how transparent | set by each person on the **Companion** page |

Everything else: [docs/configuration.md](docs/configuration.md).

## FAQ

<details>
<summary><b>Who can see my archive?</b></summary>

Only you. Each account has its own archive, enforced by PostgreSQL row-level
security. The root account manages people and settings but cannot read anyone's
files or memories. One documented exception: root can read the companion
stories a librarian writes for an account, and every such view is recorded. See
[docs/security.md](docs/security.md).
</details>

<details>
<summary><b>Where are my files stored?</b></summary>

Originals go to the bundled RustFS object store by default, or to Cloudflare R2,
any S3-compatible bucket, or local disk. The index and your memories live in
PostgreSQL on your machine. See [docs/deployment.md](docs/deployment.md).
</details>

<details>
<summary><b>Which AI models does it use?</b></summary>

The ones you add: DeepSeek, Anthropic Claude, or any OpenAI-compatible endpoint
for chat, and optionally an embedding model for search by meaning. Without an
embedding key, search still works by exact words. Each account can be assigned
its own model.
</details>

<details>
<summary><b>How do I back it up?</b></summary>

Back up the PostgreSQL database (`docker compose exec -T db pg_dump -U apsor -Fc apsor_archive > backup.dump`)
and your object storage or the `data/` folder. Nothing is ever destroyed inside
the app: replaced files and memories stay in their history.
</details>

<details>
<summary><b>What happens if my AI credits run out?</b></summary>

Uploads keep working and stay searchable by words. The missing embeddings are
filled in automatically once credits are back.
</details>

## Learn more

| | |
| --- | --- |
| [Deployment](docs/deployment.md) | Compose, Swarm, home network, storage, upgrades |
| [Configuration](docs/configuration.md) | Providers, models per account, agent and ingestion settings |
| [Features in depth](docs/features.md) | Library, memories, chat, saved questions, accounts |
| [Architecture](docs/architecture.md) | Stack, how retrieval works, data model |
| [Security and privacy](docs/security.md) | Account isolation, keys, the companion-story exception |
| [Development](docs/development.md) | Local setup, checks, project layout |
| [The librarians' world](backend/app/module/companion/lore/BIBLE.md) | The story bible behind the companions |

## Credits

Apsor Archive is designed and written by **Wei-Chun Hsiao (Alex)**.
Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
The GitHub social preview image is [docs/assets/social-preview.png](docs/assets/social-preview.png).

## License

[MIT](LICENSE) © 2026 Wei-Chun, Hsiao
