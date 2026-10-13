#!/bin/bash
# painsignals VM startup script.
# Runs as root on EVERY boot, so each step must be safe to repeat.
# Re-run by hand (to deploy new code):  sudo google_metadata_script_runner startup
#
# Instance metadata read by this script (set in Terraform):
#   git-repo        required   e.g. git@github.com:YOU/painsignals.git
#   git-ref         optional   branch or tag to run (default: main)
#   backup-bucket   optional   GCS bucket name for nightly backups
#   data-disk-name  optional   device_name of the attached persistent data disk
#
# Secrets read from Secret Manager (create the containers in Terraform, add values by hand):
#   github-deploy-key   required   private half of a read-only repo deploy key
#   github-token, anthropic-api-key, reddit-client-id, reddit-client-secret   optional

set -Eeuo pipefail
exec > >(tee -a /var/log/startup-script.log) 2>&1
on_error() { local code=$1 line=$2; echo "!! startup failed at line $line (exit $code)" >&2; }
trap 'on_error $? $LINENO' ERR

log() { echo "$(date -Is) $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

log "=== startup run ==="
export DEBIAN_FRONTEND=noninteractive

# Never run two copies at once (e.g. a manual re-run during boot)
exec 8>/run/painsignals-startup.lock
flock -n 8 || { log "another startup run is active, exiting"; exit 0; }

# ---------- config ----------
meta() { # meta <key> [default]
  curl -fs -H 'Metadata-Flavor: Google' \
    "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1" \
    || printf '%s' "${2:-}"
}
GIT_REPO="$(meta git-repo)"
GIT_REF="$(meta git-ref main)"
BACKUP_BUCKET="$(meta backup-bucket)"
DATA_DISK="$(meta data-disk-name)"
[ -n "$GIT_REPO" ] || die "instance metadata 'git-repo' is not set"

APP_USER=painsignals
APP_DIR=/opt/painsignals
DATA_MNT=/data
DATA_DIR=$DATA_MNT/painsignals
CONF_DIR=/etc/painsignals
ENV_FILE=$CONF_DIR/env
KEY_FILE=$CONF_DIR/deploy_key

as_app() { runuser -u "$APP_USER" -- "$@"; }

# ---------- packages (apt only runs if something is missing) ----------
need=()
for p in git python3 python3-venv python3-pip cron ca-certificates curl; do
  dpkg -s "$p" >/dev/null 2>&1 || need+=("$p")
done
if ((${#need[@]})); then
  log "installing: ${need[*]}"
  apt-get -o DPkg::Lock::Timeout=120 update
  apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends "${need[@]}"
fi
systemctl enable --now cron

# ---------- swap (small VMs run out of memory during pip installs) ----------
if [ ! -f /swapfile ] && [ "$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)" -lt 2048 ]; then
  log "creating 1G swapfile"
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------- app user ----------
id -u "$APP_USER" >/dev/null 2>&1 \
  || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"

# ---------- data disk (formatted only if it has no filesystem yet) ----------
mkdir -p "$DATA_MNT"
if [ -n "$DATA_DISK" ]; then
  DEV="/dev/disk/by-id/google-$DATA_DISK"
  for _ in $(seq 30); do [ -e "$DEV" ] && break; sleep 1; done
  [ -e "$DEV" ] || die "data disk $DEV is not attached (refusing to write data to the boot disk)"
  blkid "$DEV" >/dev/null 2>&1 || mkfs.ext4 -m 0 -F -L painsignals-data "$DEV"
  UUID="$(blkid -s UUID -o value "$DEV")"
  grep -q "$UUID" /etc/fstab || echo "UUID=$UUID $DATA_MNT ext4 defaults,nofail 0 2" >> /etc/fstab
  mountpoint -q "$DATA_MNT" || mount "$DATA_MNT"
else
  log "no data-disk-name set: data will live on the boot disk"
fi
install -d -o "$APP_USER" -g "$APP_USER" "$DATA_DIR" "$DATA_DIR/logs"

# ---------- secrets ----------
secret() { gcloud secrets versions access latest --secret="$1" --quiet 2>/dev/null; }
install -d -m 750 -o root -g "$APP_USER" "$CONF_DIR"
umask 077

tmp="$(mktemp -p "$CONF_DIR")"
secret github-deploy-key > "$tmp" || { rm -f "$tmp"; die "secret 'github-deploy-key' not readable"; }
install -m 600 -o "$APP_USER" -g "$APP_USER" "$tmp" "$KEY_FILE"
rm -f "$tmp"

# Env file for the app: values are shell-quoted (%q), file is readable by the app user only
tmp="$(mktemp -p "$CONF_DIR")"
{
  printf 'PS_DATA_DIR=%q\n' "$DATA_DIR"
  printf 'BACKUP_BUCKET=%q\n' "$BACKUP_BUCKET"
  for pair in GITHUB_TOKEN:github-token ANTHROPIC_API_KEY:anthropic-api-key \
              REDDIT_CLIENT_ID:reddit-client-id REDDIT_CLIENT_SECRET:reddit-client-secret; do
    var="${pair%%:*}"; name="${pair#*:}"
    if val="$(secret "$name")"; then
      printf '%s=%q\n' "$var" "$val"
    else
      log "optional secret '$name' not found, skipping $var"
    fi
  done
} > "$tmp"
install -m 600 -o "$APP_USER" -g "$APP_USER" "$tmp" "$ENV_FILE"
rm -f "$tmp"
umask 022

# ---------- code from GitHub ----------
# accept-new trusts GitHub's host key on first contact; pin it yourself if you want stricter.
GIT_SSH="ssh -i $KEY_FILE -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/home/$APP_USER/.known_hosts"
git_app() { as_app env GIT_SSH_COMMAND="$GIT_SSH" git -C "$APP_DIR" "$@"; }

install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  as_app env GIT_SSH_COMMAND="$GIT_SSH" git clone "$GIT_REPO" "$APP_DIR" || die "initial clone failed"
else
  git_app fetch --tags --prune origin || log "WARNING: git fetch failed, keeping the current checkout"
fi

if git_app rev-parse --verify -q "origin/$GIT_REF^{commit}" >/dev/null; then
  target="origin/$GIT_REF"
elif git_app rev-parse --verify -q "refs/tags/$GIT_REF^{commit}" >/dev/null; then
  target="refs/tags/$GIT_REF"
else
  die "git ref '$GIT_REF' not found"
fi
git_app checkout --force --detach "$target"
log "code at $(git_app rev-parse --short HEAD) ($GIT_REF)"

# ---------- python venv (reinstall only when requirements.txt changes) ----------
VENV="$APP_DIR/.venv"
STAMP="$VENV/.requirements.sha256"
want="$(sha256sum "$APP_DIR/requirements.txt" | cut -d' ' -f1)"
[ -x "$VENV/bin/python" ] || as_app python3 -m venv "$VENV"
if [ "$(cat "$STAMP" 2>/dev/null || true)" != "$want" ]; then
  log "installing python dependencies"
  as_app "$VENV/bin/pip" install --no-cache-dir -r "$APP_DIR/requirements.txt"
  echo "$want" | as_app tee "$STAMP" >/dev/null
fi

# ---------- job wrapper: loads env, prevents overlapping runs ----------
cat > /usr/local/bin/painsignals-run <<'EOF'
#!/bin/bash
# usage: painsignals-run collect|backup
set -euo pipefail
set -a; . /etc/painsignals/env; set +a
cd /opt/painsignals
exec 9>"$PS_DATA_DIR/.job.lock"
if ! flock -n 9; then echo "$(date -Is) another job is running, skipping ${1:-}"; exit 0; fi
case "${1:-}" in
  collect)
    echo "$(date -Is) collect start"
    exec .venv/bin/python main.py collect --sources "${PS_SOURCES:-hn,github}" --days "${PS_DAYS:-2}"
    ;;
  backup)
    [ -n "${BACKUP_BUCKET:-}" ] || { echo "no backup bucket configured"; exit 1; }
    [ -f "$PS_DATA_DIR/signals.duckdb" ] || { echo "no database yet, nothing to back up"; exit 0; }
    tmp="$(mktemp -d -p "$PS_DATA_DIR")"
    trap 'rm -rf "$tmp"' EXIT
    cp "$PS_DATA_DIR/signals.duckdb" "$tmp/signals.duckdb"
    gcloud storage cp "$tmp/signals.duckdb" "gs://$BACKUP_BUCKET/db/signals-$(date +%F).duckdb"
    if [ -d "$PS_DATA_DIR/raw" ]; then
      gcloud storage rsync --recursive "$PS_DATA_DIR/raw" "gs://$BACKUP_BUCKET/raw"
    fi
    echo "$(date -Is) backup done"
    ;;
  *)
    echo "usage: painsignals-run collect|backup" >&2
    exit 2
    ;;
esac
EOF
chmod 755 /usr/local/bin/painsignals-run

# ---------- schedule (cron.d is just a file, so this is idempotent) ----------
# Times are UTC. `extract` is deliberately NOT scheduled: it costs money, run it by hand.
cat > /etc/cron.d/painsignals <<EOF
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
0 7 * * *  $APP_USER /usr/local/bin/painsignals-run collect >> $DATA_DIR/logs/cron.log 2>&1
30 7 * * * $APP_USER /usr/local/bin/painsignals-run backup  >> $DATA_DIR/logs/cron.log 2>&1
EOF
chmod 644 /etc/cron.d/painsignals

cat > /etc/logrotate.d/painsignals <<EOF
$DATA_DIR/logs/*.log {
  weekly
  rotate 8
  compress
  missingok
  notifempty
}
EOF

log "=== startup complete ==="