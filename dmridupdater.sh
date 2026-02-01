#!/bin/bash

DMRIDFILE="/var/lib/mmdvm/DMRIds.dat"
DMRFILEBACKUP=1



URL="https://raw.githubusercontent.com/DMR-Database/database-beta/master/DMRIds.dat"

set -o pipefail

# Must be root
if [ "$(id -u)" != "0" ]; then
  echo "This script must be run as root" 1>&2
  exit 1
fi

# Backup existing file (only if it exists)
if [ "$DMRFILEBACKUP" -ne 0 ] && [ -f "$DMRIDFILE" ]; then
  cp -f "$DMRIDFILE" "${DMRIDFILE}.$(date +%d%m%y)"
fi

# Prune backups safely
if [ "$DMRFILEBACKUP" -ne 0 ]; then
  backups=( "${DMRIDFILE}."* )
  if [ -e "${backups[0]}" ]; then
    BACKUPCOUNT="${#backups[@]}"
    if [ "$BACKUPCOUNT" -gt "$DMRFILEBACKUP" ]; then
      # delete oldest first
      ls -tr "${DMRIDFILE}."* | head -n $((BACKUPCOUNT - DMRFILEBACKUP)) | while read -r f; do
        rm -f "$f"
      done
    fi
  fi
fi

# Download -> temp -> validate non-empty -> install
tmpfile="$(mktemp)"
if curl -fLsS "$URL" | sed -e 's/[[:space:]]\+/ /g' > "$tmpfile" && [ -s "$tmpfile" ]; then
  mv -f "$tmpfile" "$DMRIDFILE"
else
  echo "DMR ID download failed; keeping existing $DMRIDFILE" 1>&2
  rm -f "$tmpfile"
  exit 1
fi


