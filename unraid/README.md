# Stellenpilot on Unraid (fork)

This stack runs the full dashboard, an HTTPS gateway, and an **optional** once-per-day
search scheduler. It does not publish the unprotected dashboard port to the host.
Source fork: https://github.com/RoWe90/stellenpilot

## Requirements

- Unraid 7.x with Docker Compose (`docker compose version`), or Compose Manager Plus.
- A fixed LAN IP or local DNS name for your Unraid server.
- A free TCP port for the gateway (default `8443`; `18443` is a common alternative). **Do not port-forward** it.
- Enough disk space for PDFs and, optionally, built-in AI weights (several GB).
- A strong HTTPS gateway password; the generated CA certificate must be trusted in browsers.

## Installation

From the **Unraid terminal**, clone this fork's default `main` branch:

```bash
cd /mnt/user/appdata
git clone https://github.com/RoWe90/stellenpilot.git stellenpilot-source
cd stellenpilot-source/unraid
cp .env.example .env
mkdir -p /mnt/user/appdata/stellenpilot
chown -R 1000:1000 /mnt/user/appdata/stellenpilot
docker run -it --rm caddy:2.10-alpine caddy hash-password
```

The last command prompts for a password and prints its hash. **Do not paste
the following commands while the password prompt or initialization is still
running**: the interactive process may consume them as input.

Edit the Compose environment file from inside `stellenpilot-source/unraid`:

```bash
TERM=xterm nano .env
```

Some Unraid terminals (including Ghostty) set `TERM=xterm-ghostty`, which
Unraid's version of `nano` may not recognize. Prefixing the command with
`TERM=xterm` fixes this. If it still fails, try `TERM=xterm vi .env`.

- `STELLENPILOT_HOST`: your Unraid LAN IP or DNS name, **without** scheme or port.
- `STELLENPILOT_HTTPS_PORT`: external HTTPS port. The supplied `.env.example` uses `18443` to avoid collisions with existing Unraid services; change it to another free port if needed. The container still listens on `8443` internally.
- `CADDY_PASSWORD_HASH`: the entire generated password hash in **single quotes**.
- `STELLENPILOT_DATA_DIR`: persistent appdata folder; defaults to `/mnt/user/appdata/stellenpilot`.
- `PUID` and `PGID`: the UID/GID that owns the appdata folder (default 1000:1000).
- `STELLENPILOT_DAILY_TIME`: optional search time (e.g. `08:45`, Europe/Berlin).

The gateway login username is **stellenpilot**. The password is the one you just hashed.
The hash is not your OpenCode key.

**Save the file before continuing.** Replace the example IP and
`CADDY_PASSWORD_HASH='REPLACE_ME'` with your actual LAN host and the entire
password hash, retaining the **single quotes** around the hash. Never share
your password or API keys in a log.

Validate the environment and build the image:

```bash
cd /mnt/user/appdata/stellenpilot-source/unraid || exit 1

if grep -q REPLACE_ME .env; then
  echo "ERROR: replace CADDY_PASSWORD_HASH in .env first"
else
  docker compose config --quiet && docker compose build
fi
```

**Run initialization and wait for the shell prompt to return.** The
`</dev/null` prevents accidentally pasted commands from being consumed by
the temporary `docker compose run` container:

```bash
docker compose run --rm -T stellenpilot init </dev/null
```

Only **after** that command has finished, start the long-running services
(the image has already been built):

```bash
docker compose up -d --no-build
docker compose ps
docker compose logs --tail=60 stellenpilot gateway
```

If startup fails with `failed to bind host port 0.0.0.0:8443/tcp: address already in use`,
another service is using the external port. Do **not** stop that service.
Set `STELLENPILOT_HTTPS_PORT=18443` (or another free port) in
`unraid/.env`, then rerun `docker compose up -d --no-build`.
The internal `Caddyfile` port stays `8443`; the Unraid WebUI link follows
the chosen external port automatically.

You should see both `Stellenpilot` (healthy) and
`Stellenpilot-Gateway` (running). The `init` command alone does not start
the gateway. If you see `No such container: Stellenpilot-Gateway`, first
run `docker compose ps -a` and check `docker compose logs gateway`. Do
not try to export the TLS certificate until the gateway exists and has
started successfully.

The commands build directly from this fork's checked-out source; they do not
require a previously published image. The fork's GitHub Actions workflow may
also publish `ghcr.io/rowe90/stellenpilot:latest` after a successful build,
but rebuilding locally is the most predictable option. Rebuild after pulling
new code.

## Browser access and TLS

Open `https://<YOUR-UNRAID-LAN-IP>:18443/` (or use the port configured in `STELLENPILOT_HTTPS_PORT`).
**Caddy uses an internal certificate authority.** A new browser will not trust
it by default. Before entering your password, export the root CA:

```bash
docker cp Stellenpilot-Gateway:/data/caddy/pki/authorities/local/root.crt \
  /mnt/user/appdata/stellenpilot/stellenpilot-root.crt
```

Copy the public root certificate from Unraid to each client (for example,
`scp root@TARDIS:/mnt/user/appdata/stellenpilot/stellenpilot-root.crt .`).
Import it as a **trusted local CA** on every device that will use the
dashboard. For Fedora/Nobara, from the downloaded certificate directory:

```bash
sudo cp stellenpilot-root.crt /etc/pki/ca-trust/source/anchors/stellenpilot-root.crt
sudo update-ca-trust
```

Browsers may have their own certificate store. Keep the local CA private key
(`.../caddy/data/caddy/pki/authorities/local/root.key`) protected and backed up.
Never distribute that private key. Do not disable certificate validation as a
permanent workaround.

All browser traffic goes through Caddy HTTPS and Basic authentication. Caddy
rewrites the upstream Host/Origin headers to localhost **only within the private
Compose network** because Stellenpilot currently rejects remote hosts. The
original server port `8765` has **no host port mapping**. Do not expose it via
Unraid or another Docker network. A health probe returns only `{"ok":true}`.

## Automatic searches

Run the scheduler as an **optional sidecar**:

```bash
cd /mnt/user/appdata/stellenpilot-source/unraid
docker compose --profile scheduler up -d
docker compose logs -f scheduler
```

It runs `stellenpilot --home /data run` at the configured local time each day.
It records the date in `/data/.unraid-scheduler-last-run`, avoiding a second
daily run after restarts. A missed start runs when the sidecar next wakes.
Scheduler failures are logged; automatic retry waits until the next day.

Do **not** also schedule the same command in Unraid User Scripts or another cron
job, and avoid manually starting a dashboard search during the scheduled run.
The desktop application's built-in scheduler is unavailable inside Docker.

To stop only the scheduler: `docker compose --profile scheduler stop scheduler`.
To manually run once: `docker compose run --rm stellenpilot run`.

## OpenCode Go API

In the dashboard choose **Settings → AI model → OpenCode Go**.

- Model: `deepseek-v4.1-flash` (chat-completions model).
- API key: your OpenCode Go key.
- Default endpoint: `https://opencode.ai/zen/go/v1/chat/completions`.
- The app sends `x-opencode-session` with a stable UUID per LLM instance.

Alternatively set `[llm]` in `/mnt/user/appdata/stellenpilot/config.toml`:

```toml
[llm]
provider = "opencode"
model = "deepseek-v4.1-flash"
```

Store `OPENCODE_API_KEY=...` in the **application's** private
`/mnt/user/appdata/stellenpilot/.env` (different from `unraid/.env`).
Never commit either .env file.

**Compatibility note:** OpenCode Go explicitly targets coding agents. This
integration uses its documented API and required session header, but job search
and CV-generation traffic may not be allowed or reliably served; this fork
does not bypass rate limits or provider restrictions. It currently supports
OpenCode models with the OpenAI-style **chat/completions** API, not models that
only expose Anthropic Messages or OpenAI Responses.

## Alternative: Ollama on another machine

If your Unraid CPU is too slow for inference, run Ollama on a workstation
instead. Configure `llm.provider = "ollama"`, the exact model name, and
`llm.base_url = "http://<WORKSTATION-LAN-IP>:11434"` in `config.toml`.
Make sure the workstation's Ollama listens on the LAN interface and a firewall
restricts access to your trusted network. No Ollama GPU is needed on Unraid.

## Operations

```bash
cd /mnt/user/appdata/stellenpilot-source/unraid
docker compose ps
docker compose logs --tail=100 stellenpilot gateway
docker compose run --rm stellenpilot doctor
docker compose --profile scheduler down
# After reviewing upstream changes:
git pull --ff-only
docker compose --profile scheduler up -d --build
```

Keep backups of `STELLENPILOT_DATA_DIR` (profile, config, DB, documents, keys,
model data and gateway CA). Do not expose `unraid/.env` or application `.env`.

**Verification limits:** unit tests mock OpenCode calls. They do not establish
live entitlement, rate-limit behavior, real OpenCode responses, or a complete
Unraid browser deployment. Test these on your own server before relying on it.
