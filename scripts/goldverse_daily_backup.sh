#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/odoo/AimAze-Laundry-ERP-GoldVerse"
BACKUP_ROOT="/opt/odoo/backups/goldverse_daily"
STAGING_DIR="$BACKUP_ROOT/current"
ARCHIVE_PATH="$BACKUP_ROOT/goldverse_premium_laundry_daily.tar.gz"
ARCHIVE_TMP="$ARCHIVE_PATH.tmp"
CONFIG_FILE="/etc/odoo/goldverse_premium_laundry.conf"
DATA_DIR="/var/lib/odoo/goldverse_premium_laundry"
FILESTORE_DIR="$DATA_DIR/filestore/goldverse_premium_laundry"
DB_NAME="goldverse_premium_laundry"
GIT_REMOTE="origin"
GIT_BRANCH="main"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

cleanup() {
    rm -rf "$STAGING_DIR"
    rm -f "$ARCHIVE_TMP"
}

sync_vps_repo_to_github() {
    if [[ ! -d "$APP_DIR/.git" ]]; then
        log "Skipping Git sync because $APP_DIR is not a Git repository."
        return 0
    fi

    local commit_needed=0
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"

    if sudo -u odoo git -C "$APP_DIR" diff --quiet --ignore-submodules HEAD -- && \
       [[ -z "$(sudo -u odoo git -C "$APP_DIR" ls-files --others --exclude-standard)" ]]; then
        log "VPS repo has no uncommitted changes. GitHub sync not needed."
        return 0
    fi

    log "Detected tracked VPS repo changes. Syncing live VPS state to GitHub before backup."
    sudo -u odoo git -C "$APP_DIR" add -A

    if ! sudo -u odoo git -C "$APP_DIR" diff --cached --quiet --ignore-submodules --; then
        commit_needed=1
    fi

    if [[ "$commit_needed" -eq 1 ]]; then
        sudo -u odoo git -C "$APP_DIR" commit -m "Auto-sync VPS changes before daily backup ($timestamp)"
    fi

    sudo -u odoo git -C "$APP_DIR" push "$GIT_REMOTE" "$GIT_BRANCH"
    log "Live VPS repo changes pushed to GitHub."
}

main() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        echo "This script must run as root." >&2
        exit 1
    fi

    trap cleanup EXIT

    log "Starting GoldVerse daily backup."
    mkdir -p "$BACKUP_ROOT"
    chmod 750 "$BACKUP_ROOT"

    if ! sync_vps_repo_to_github; then
        log "WARNING: GitHub sync failed. Continuing with backup so data protection is not skipped."
    fi

    rm -rf "$STAGING_DIR"
    mkdir -p \
        "$STAGING_DIR/database" \
        "$STAGING_DIR/filestore" \
        "$STAGING_DIR/config" \
        "$STAGING_DIR/meta"

    log "Creating PostgreSQL dump for $DB_NAME."
    sudo -u postgres pg_dump -Fc "$DB_NAME" > "$STAGING_DIR/database/${DB_NAME}.dump"

    log "Copying filestore."
    rsync -a --delete "$FILESTORE_DIR/" "$STAGING_DIR/filestore/${DB_NAME}/"

    log "Copying Odoo config."
    install -m 600 "$CONFIG_FILE" "$STAGING_DIR/config/$(basename "$CONFIG_FILE")"

    log "Writing backup manifest."
    cat > "$STAGING_DIR/meta/backup_manifest.txt" <<EOF
backup_name=goldverse_premium_laundry_daily
created_at=$(date '+%Y-%m-%d %H:%M:%S %Z')
database=$DB_NAME
config_file=$CONFIG_FILE
data_dir=$DATA_DIR
filestore_dir=$FILESTORE_DIR
repo_path=$APP_DIR
repo_commit=$(sudo -u odoo git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo "unavailable")
host=$(hostname -f 2>/dev/null || hostname)
EOF

    log "Compressing backup archive."
    tar -C "$STAGING_DIR" -czf "$ARCHIVE_TMP" .
    mv -f "$ARCHIVE_TMP" "$ARCHIVE_PATH"
    chmod 640 "$ARCHIVE_PATH"

    log "Backup completed: $ARCHIVE_PATH"
}

main "$@"
