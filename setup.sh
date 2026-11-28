#!/usr/bin/env bash
# Apsor Archive setup wizard.
#
# Asks a few questions and writes the deployment configuration so nobody has to
# hand-edit environment variables:
#   .env                         non-secret settings (Compose interpolation and
#                                the host-run API both read it)
#   .secrets/*.env               provider and object-store credentials the app
#                                reads itself (never container environment)
#   secrets/*.txt                files Compose mounts as Docker secrets
#
# Usage:
#   ./setup.sh               interactive (also: ./start.sh setup, make setup)
#   ./setup.sh --defaults    non-interactive: production + bundled RustFS
#   ./setup.sh --defaults --dev   non-interactive: local development
#
# Generated credentials are never printed. Existing files are kept unless you
# confirm an overwrite (in --defaults mode they are always kept).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Container users that read the mounted secret files.
APP_UID=10001        # API, worker, and RustFS images
TUNNEL_UID=65532     # cloudflared image

NONINTERACTIVE=false
MODE=""
for arg in "$@"; do
  case "$arg" in
    --defaults | -y) NONINTERACTIVE=true ;;
    --dev) MODE="dev" ;;
    --production) MODE="production" ;;
    -h | --help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see --help)" >&2
      exit 2
      ;;
  esac
done
if [[ ! -t 0 ]]; then
  NONINTERACTIVE=true
fi

PENDING_SUDO=()
WRITTEN=()
KEPT=()

say() { printf '%s\n' "$*"; }
heading() { printf '\n== %s ==\n' "$*"; }

# ask VAR "Question" "default"
# Locals use a __ prefix so printf -v never targets a shadowing local.
ask() {
  local __var="$1" __prompt="$2" __default="${3:-}" __reply=""
  if [[ "$NONINTERACTIVE" == true ]]; then
    printf -v "$__var" '%s' "$__default"
    return
  fi
  if [[ -n "$__default" ]]; then
    read -r -p "$__prompt [$__default]: " __reply
  else
    read -r -p "$__prompt: " __reply
  fi
  printf -v "$__var" '%s' "${__reply:-$__default}"
}

# ask_secret VAR "Question" — input is not echoed and never printed back.
ask_secret() {
  local __var="$1" __prompt="$2" __reply=""
  if [[ "$NONINTERACTIVE" == true ]]; then
    printf -v "$__var" '%s' ""
    return
  fi
  read -r -s -p "$__prompt (input hidden, Enter to skip): " __reply
  printf '\n'
  printf -v "$__var" '%s' "$__reply"
}

# ask_choice VAR "Question" default option...
ask_choice() {
  local __var="$1" __prompt="$2" __default="$3" __answer="" __option=""
  shift 3
  local __options=("$@")
  while true; do
    ask __answer "$__prompt ($(IFS=/; echo "${__options[*]}"))" "$__default"
    __answer="$(printf '%s' "$__answer" | tr '[:upper:]' '[:lower:]')"
    for __option in "${__options[@]}"; do
      if [[ "$__answer" == "$__option" ]]; then
        printf -v "$__var" '%s' "$__answer"
        return
      fi
    done
    if [[ "$NONINTERACTIVE" == true ]]; then
      echo "Invalid default for: $__prompt" >&2
      exit 2
    fi
    say "Please answer one of: ${__options[*]}"
  done
}

confirm() {
  local prompt="$1" default="${2:-n}" reply=""
  if [[ "$NONINTERACTIVE" == true ]]; then
    [[ "$default" == "y" ]]
    return
  fi
  local hint="y/N"
  [[ "$default" == "y" ]] && hint="Y/n"
  read -r -p "$prompt [$hint]: " reply
  reply="${reply:-$default}"
  [[ "$reply" =~ ^[Yy] ]]
}

random_hex() {
  od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'
}

# may_write PATH — true when PATH is absent or the user agrees to replace it.
may_write() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    return 0
  fi
  if [[ "$NONINTERACTIVE" != true ]] && confirm "$path already exists. Overwrite it?" n; then
    return 0
  fi
  KEPT+=("$path")
  return 1
}

# write_file PATH MODE — content on stdin; written atomically with umask 077.
# Call it with a redirect, never at the end of a pipe: it records WRITTEN.
write_file() {
  local path="$1" mode="$2" tmp
  tmp="$(umask 077 && mktemp "${path}.XXXXXX")"
  cat >"$tmp"
  chmod "$mode" "$tmp"
  mv -f "$tmp" "$path"
  WRITTEN+=("$path")
}

# share_with_group PATH GID — let one container uid read a 0640 secret file.
share_with_group() {
  local path="$1" gid="$2"
  if ! chgrp "$gid" "$path" 2>/dev/null; then
    PENDING_SUDO+=("sudo chgrp $gid $path")
  fi
}

# ---------------------------------------------------------------- questions
heading "Apsor Archive setup"
say "Press Enter to accept the value in brackets."

if [[ -z "$MODE" ]]; then
  ask_choice MODE "Deployment mode: production (Docker Compose + Cloudflare Tunnel) or dev (host-run API)" \
    production production dev
fi

if [[ "$MODE" == "production" ]]; then
  ask PUBLIC_HOST "Public hostname served through the tunnel" "archive.example.com"
  ask_choice STORAGE "Original-file storage: rustfs (bundled), r2 (Cloudflare R2), s3 (any S3), local" \
    rustfs rustfs r2 s3 local
  COOKIE_SECURE=true
else
  PUBLIC_HOST="archive.example.com"
  ask_choice STORAGE "Original-file storage: local (data/ folder), rustfs (dev container), r2, s3" \
    local local rustfs r2 s3
  COOKIE_SECURE=false
fi
ask SESSION_TTL_HOURS "Sign-in session lifetime in hours" "720"
if ! [[ "$SESSION_TTL_HOURS" =~ ^[0-9]+$ ]] || (( SESSION_TTL_HOURS < 1 )); then
  say "Session lifetime must be a positive number of hours; using 720."
  SESSION_TTL_HOURS=720
fi

R2_ENDPOINT="" R2_BUCKET="apsor-archive" R2_KEY="" R2_SECRET=""
S3_ENDPOINT="" S3_BUCKET="apsor-archive" S3_REGION="us-east-1" S3_STYLE="path"
S3_CREATE="true" S3_KEY="" S3_SECRET=""
case "$STORAGE" in
  r2)
    heading "Cloudflare R2"
    ask R2_ENDPOINT "R2 account endpoint" "https://<account-id>.r2.cloudflarestorage.com"
    ask R2_BUCKET "Bucket name" "apsor-archive"
    ask_secret R2_KEY "R2 access key ID"
    ask_secret R2_SECRET "R2 secret access key"
    ;;
  s3)
    heading "S3-compatible storage"
    ask S3_ENDPOINT "S3 endpoint URL" "https://s3.us-east-1.amazonaws.com"
    ask S3_BUCKET "Bucket name" "apsor-archive"
    ask S3_REGION "Region" "us-east-1"
    ask_choice S3_STYLE "Addressing style" path path virtual
    if confirm "Create the bucket automatically if it is missing?" n; then
      S3_CREATE=true
    else
      S3_CREATE=false
    fi
    ask_secret S3_KEY "Access key ID"
    ask_secret S3_SECRET "Secret access key"
    ;;
  rustfs)
    # Production credentials for the bundled store are generated, never typed
    # or shown.
    if [[ "$MODE" == "production" ]]; then
      S3_KEY="apsor$(random_hex 8)"
      S3_SECRET="$(random_hex 24)"
      S3_ENDPOINT="http://rustfs:9000"
    else
      # Demo pair baked into docker-compose.dev.yml; development only.
      S3_KEY="apsor-dev"
      S3_SECRET="apsor-dev-secret"
      S3_ENDPOINT="http://127.0.0.1:59000"
      S3_BUCKET="apsor-archive-dev"
    fi
    ;;
esac

heading "AI provider (optional)"
say "Chat models can also be configured later in Settings > Providers."
ask_secret DEEPSEEK_KEY "DeepSeek API key"

TUNNEL_TOKEN=""
if [[ "$MODE" == "production" ]]; then
  heading "Cloudflare Tunnel"
  say "Paste the tunnel token from the Cloudflare dashboard (or skip and create"
  say "secrets/cf_token.txt later; see docs/cloudflare-tunnel.md)."
  ask_secret TUNNEL_TOKEN "Tunnel token"
fi

# RabbitMQ only reads its default user on first boot. Keep the demo pair when a
# broker volume already exists, otherwise the stored user would stop matching.
RABBIT_USER="apsor" RABBIT_PASS="apsor"
if [[ "$MODE" == "production" ]]; then
  if command -v docker >/dev/null 2>&1 \
    && docker volume inspect apsor-archive_rabbitmq-data >/dev/null 2>&1; then
    say "An existing RabbitMQ volume was found; keeping its current credentials."
    RABBIT_USER="" RABBIT_PASS=""
  else
    RABBIT_PASS="$(random_hex 16)"
  fi
fi

# ------------------------------------------------------------------- writes
heading "Writing configuration"
mkdir -p .secrets secrets
# The containers traverse these directories as a different uid.
chmod 755 .secrets secrets

if may_write .env; then
  write_env() {
    say "# Written by ./setup.sh. Non-secret settings only; credentials live in"
    say "# .secrets/*.env and secrets/*.txt (see secrets/README.md)."
    say "APSOR_PUBLIC_HOST=$PUBLIC_HOST"
    say "APSOR_COOKIE_SECURE=$COOKIE_SECURE"
    say "APSOR_SESSION_TTL_HOURS=$SESSION_TTL_HOURS"
    say "APSOR_STORAGE_BACKEND=$STORAGE"
    case "$STORAGE" in
      rustfs)
        if [[ "$MODE" == "production" ]]; then
          say "# Starts the bundled RustFS service in docker-compose.yml."
          say "COMPOSE_PROFILES=rustfs"
        else
          say "# Start it with: docker compose -f docker-compose.dev.yml --profile rustfs up -d"
        fi
        say "APSOR_S3_ENDPOINT_URL=$S3_ENDPOINT"
        say "APSOR_S3_BUCKET=$S3_BUCKET"
        say "APSOR_S3_CREATE_BUCKET=true"
        ;;
      r2)
        say "APSOR_R2_ENDPOINT_URL=$R2_ENDPOINT"
        say "APSOR_R2_BUCKET=$R2_BUCKET"
        ;;
      s3)
        say "APSOR_S3_ENDPOINT_URL=$S3_ENDPOINT"
        say "APSOR_S3_BUCKET=$S3_BUCKET"
        say "APSOR_S3_REGION=$S3_REGION"
        say "APSOR_S3_ADDRESSING_STYLE=$S3_STYLE"
        say "APSOR_S3_CREATE_BUCKET=$S3_CREATE"
        ;;
    esac
    if [[ "$MODE" == "production" ]]; then
      if [[ -n "$RABBIT_USER" ]]; then
        say "# Broker credentials for the Compose network only."
        say "RABBITMQ_DEFAULT_USER=$RABBIT_USER"
        say "RABBITMQ_DEFAULT_PASS=$RABBIT_PASS"
      fi
    else
      say "# docker-compose.dev.yml publishes RabbitMQ on 127.0.0.1 with demo credentials."
      say "APSOR_RABBITMQ_ENABLED=true"
      say "APSOR_RABBITMQ_URL=amqp://apsor:apsor@127.0.0.1:5672/"
    fi
  }
  write_file .env 600 < <(write_env)
fi

if [[ "$STORAGE" == "rustfs" || "$STORAGE" == "s3" ]]; then
  if [[ -n "$S3_KEY" && -n "$S3_SECRET" ]]; then
    if may_write .secrets/s3.env; then
      write_file .secrets/s3.env 640 < <(printf 'APSOR_S3_ACCESS_KEY_ID=%s\nAPSOR_S3_SECRET_ACCESS_KEY=%s\n' "$S3_KEY" "$S3_SECRET")
      share_with_group .secrets/s3.env "$APP_UID"
    fi
  else
    say "No S3 credentials entered: create .secrets/s3.env before starting (see secrets/README.md)."
  fi
fi

if [[ "$STORAGE" == "rustfs" && "$MODE" == "production" ]]; then
  # RustFS reads the same pair as Docker secrets. Rewrite them only together
  # with .secrets/s3.env so the two copies can never disagree.
  if [[ " ${WRITTEN[*]} " == *" .secrets/s3.env "* ]]; then
    write_file secrets/rustfs_access_key.txt 640 < <(printf '%s' "$S3_KEY")
    write_file secrets/rustfs_secret_key.txt 640 < <(printf '%s' "$S3_SECRET")
    share_with_group secrets/rustfs_access_key.txt "$APP_UID"
    share_with_group secrets/rustfs_secret_key.txt "$APP_UID"
  elif [[ ! -e secrets/rustfs_access_key.txt || ! -e secrets/rustfs_secret_key.txt ]]; then
    say "secrets/rustfs_*_key.txt are missing but .secrets/s3.env was kept."
    say "Create them with the same access key pair, or rerun and overwrite .secrets/s3.env."
  fi
fi

if [[ "$STORAGE" == "r2" ]]; then
  if [[ -n "$R2_KEY" && -n "$R2_SECRET" ]]; then
    if may_write .secrets/r2.env; then
      write_file .secrets/r2.env 640 < <(printf 'APSOR_R2_ACCESS_KEY_ID=%s\nAPSOR_R2_SECRET_ACCESS_KEY=%s\n' "$R2_KEY" "$R2_SECRET")
      share_with_group .secrets/r2.env "$APP_UID"
    fi
  elif [[ ! -e .secrets/r2.env ]]; then
    say "No R2 credentials entered: create .secrets/r2.env before starting (see secrets/README.md)."
  fi
fi

if [[ -n "$DEEPSEEK_KEY" ]] && may_write .secrets/deepseek.env; then
  write_file .secrets/deepseek.env 640 < <(printf 'APSOR_DEEPSEEK_API_KEY=%s\n' "$DEEPSEEK_KEY")
  share_with_group .secrets/deepseek.env "$APP_UID"
fi

if [[ "$MODE" == "production" ]]; then
  if [[ -n "$TUNNEL_TOKEN" ]] && may_write secrets/cf_token.txt; then
    write_file secrets/cf_token.txt 640 < <(printf '%s' "$TUNNEL_TOKEN")
    share_with_group secrets/cf_token.txt "$TUNNEL_UID"
  elif [[ ! -e secrets/cf_token.txt ]]; then
    say "secrets/cf_token.txt is missing; Compose needs it before 'docker compose up'."
  fi
fi

# Never keep secrets in shell variables longer than needed.
unset R2_KEY R2_SECRET S3_KEY S3_SECRET DEEPSEEK_KEY TUNNEL_TOKEN RABBIT_PASS

# ------------------------------------------------------------------ summary
heading "Done"
for path in "${WRITTEN[@]}"; do say "  wrote  $path"; done
for path in "${KEPT[@]}"; do say "  kept   $path (unchanged)"; done

if ((${#PENDING_SUDO[@]} > 0)); then
  say ""
  say "The containers read secret files through a shared group. Run:"
  for command in "${PENDING_SUDO[@]}"; do say "  $command"; done
  if [[ "$NONINTERACTIVE" != true ]] && confirm "Run these commands with sudo now?" n; then
    for command in "${PENDING_SUDO[@]}"; do
      # shellcheck disable=SC2086
      $command
    done
  fi
fi

say ""
if [[ "$MODE" == "production" ]]; then
  say "Next: docker compose up -d --build   (or: make up)"
  say "Then open https://$PUBLIC_HOST and create the root account before sharing the link."
else
  say "Next: ./start.sh   (starts dev dependencies, the API, and the ingestion worker)"
fi
