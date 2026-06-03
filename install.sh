#!/usr/bin/env bash
# install.sh — wire icloud-mail + icloud-cal MCP servers into ~/.claude.json
#
# Usage:
#   ./install.sh                  # interactive
#   ICLOUD_USER=... ICLOUD_APP_PASSWORD=... ./install.sh    # non-interactive
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_JSON="${CLAUDE_JSON:-$HOME/.claude.json}"

say()  { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m!!\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31mxx\033[0m %s\n" "$*" >&2; exit 1; }

# ── 1. uv ───────────────────────────────────────────────────────────────
if ! command -v uv >/dev/null && ! [ -x "$HOME/.local/bin/uv" ]; then
  say "Installing uv (Python package runner)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UVX="$(command -v uvx || echo "$HOME/.local/bin/uvx")"
[ -x "$UVX" ] || die "uvx not found after install"

# ── 2. CA bundle (Python on macOS doesn't trust the system keychain) ───
if   [ -f /etc/ssl/cert.pem ];                         then CERT=/etc/ssl/cert.pem
elif [ -f /etc/ssl/certs/ca-certificates.crt ];        then CERT=/etc/ssl/certs/ca-certificates.crt
elif [ -f /etc/pki/tls/certs/ca-bundle.crt ];          then CERT=/etc/pki/tls/certs/ca-bundle.crt
else die "Couldn't find a system CA bundle — set CERT manually in install.sh"
fi
say "CA bundle: $CERT"

# ── 3. credentials ──────────────────────────────────────────────────────
EMAIL="${ICLOUD_USER:-}"
PWD_="${ICLOUD_APP_PASSWORD:-}"
if [ -z "$EMAIL" ]; then read -rp "iCloud email (e.g. you@me.com): " EMAIL; fi
if [ -z "$PWD_" ]; then
  echo "App-specific password — generate at https://appleid.apple.com → Sign-In and Security → App-Specific Passwords"
  read -rsp "App-specific password (input hidden): " PWD_; echo
fi
[ -n "$EMAIL" ] && [ -n "$PWD_" ] || die "Email and password are required"

# ── 4. merge into ~/.claude.json ────────────────────────────────────────
[ -f "$CLAUDE_JSON" ] || echo '{}' > "$CLAUDE_JSON"
cp "$CLAUDE_JSON" "$CLAUDE_JSON.bak.$(date +%s)" || true
say "Backed up existing config to $CLAUDE_JSON.bak.*"

python3 - "$CLAUDE_JSON" "$EMAIL" "$PWD_" "$CERT" "$REPO_DIR" "$UVX" <<'PY'
import json, sys
path, email, pwd, cert, repo, uvx = sys.argv[1:7]
with open(path) as f:
    cfg = json.load(f)
cfg.setdefault("mcpServers", {})
cfg["mcpServers"]["icloud-mail"] = {
    "type": "stdio",
    "command": uvx,
    "args": ["mcp-email-server@latest", "stdio"],
    "env": {
        "MCP_EMAIL_SERVER_IMAP_HOST": "imap.mail.me.com",
        "MCP_EMAIL_SERVER_IMAP_PORT": "993",
        "MCP_EMAIL_SERVER_IMAP_USER_NAME": email,
        "MCP_EMAIL_SERVER_IMAP_PASSWORD": pwd,
        "MCP_EMAIL_SERVER_SMTP_HOST": "smtp.mail.me.com",
        "MCP_EMAIL_SERVER_SMTP_PORT": "587",
        "MCP_EMAIL_SERVER_SMTP_USER_NAME": email,
        "MCP_EMAIL_SERVER_SMTP_PASSWORD": pwd,
        "SSL_CERT_FILE": cert,
        "REQUESTS_CA_BUNDLE": cert,
    },
}
cfg["mcpServers"]["icloud-cal"] = {
    "type": "stdio",
    "command": uvx,
    "args": [
        "--with", "caldav", "--with", "vobject", "--with", "mcp",
        "python", f"{repo}/server.py",
    ],
    "env": {
        "ICLOUD_USER": email,
        "ICLOUD_APP_PASSWORD": pwd,
        "SSL_CERT_FILE": cert,
        "REQUESTS_CA_BUNDLE": cert,
    },
}
with open(path, "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print("✓ wrote", path)
PY

# ── 5. smoke test ───────────────────────────────────────────────────────
say "Smoke-testing CalDAV connection…"
SSL_CERT_FILE="$CERT" ICLOUD_USER="$EMAIL" ICLOUD_APP_PASSWORD="$PWD_" \
  "$UVX" --with caldav --with vobject --with mcp python -c "
import sys; sys.path.insert(0, '$REPO_DIR')
import server
cals = [c.get_display_name() for c in server.principal().calendars()]
print(f'✓ {len(cals)} calendars:', cals[:5], '…' if len(cals)>5 else '')
" 2>&1 | tail -5

say "Done. Restart Claude Code — tools mcp__icloud-mail__* and mcp__icloud-cal__* will appear."
