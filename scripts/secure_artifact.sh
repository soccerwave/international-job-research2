#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: secure_artifact.sh pack <base-dir> <output.enc> <path>... | unpack <input.enc> <dest-dir>" >&2
  exit 2
}

: "${ARTIFACT_ENCRYPTION_KEY:?ARTIFACT_ENCRYPTION_KEY must be set}"

mode="${1:-}"
case "$mode" in
  pack)
    [ "$#" -ge 4 ] || usage
    base_dir="$2"
    output="$3"
    shift 3
    mkdir -p "$(dirname "$output")"
    (
      cd "$base_dir"
      tar -czf - "$@"
    ) | openssl enc -aes-256-cbc -pbkdf2 -salt \
        -pass env:ARTIFACT_ENCRYPTION_KEY \
        -out "$output"
    ;;
  unpack)
    [ "$#" -eq 3 ] || usage
    input="$2"
    dest_dir="$3"
    mkdir -p "$dest_dir"
    openssl enc -d -aes-256-cbc -pbkdf2 \
      -pass env:ARTIFACT_ENCRYPTION_KEY \
      -in "$input" | tar -xzf - -C "$dest_dir"
    ;;
  *)
    usage
    ;;
esac
