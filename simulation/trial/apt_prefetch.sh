#!/usr/bin/env bash
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# apt_prefetch.sh PKG... - put every .deb that
#     apt-get install --no-install-recommends PKG...
# would download into apt's archive cache first: several files at a time and,
# for files of a snapshot.ubuntu.com snapshot, from an ordinary Ubuntu mirror
# when it has the identical file. The install that follows then downloads
# nothing, or only what this script could not get. Needs write access to the
# archive cache (root); called by install_deps.sh.
#
# Why: snapshot.ubuntu.com serves one file at a time slowly (~2 s per file on
# a good day: 399 MB took 16 min) and on 2026-10-13 it fell to ~50 kB/s with
# HTTP 503s, so the CI install failed after two hours.
#
# Pinning is unchanged. Names, sizes and SHA256 of the files come from the
# package index apt already holds (signature-checked against the Signed-By
# key; in CI the dated snapshot), via apt-get --print-uris. A file enters the
# cache only when its size and SHA256 match, whichever server sent it, so the
# installed bytes are exactly the ones the pinned index names. Files already in
# the cache (e.g. restored by actions/cache) are hashed too: apt itself accepts
# a cached .deb whose size matches without checking its hash.
#
# Sources per file, in this order:
#   1. pool file of a snapshot.ubuntu.com snapshot: the same pool path on each
#      mirror in UBUNTU_POOL_MIRRORS (a mirror keeps a version until it is
#      superseded, so it has nearly all of them; the rest are 404s). A mirror
#      that delivers none of the first few files is skipped.
#   2. the URI apt chose itself (the snapshot, packages.osrfoundation.org, ...).
# Whatever is still missing is left to apt-get install, which fetches it from
# its own source with its own retries. So this script only makes the install
# faster: it exits 0 even when it fetched nothing (2 = called wrongly).
#
# Environment:
#   UBUNTU_POOL_MIRRORS         space-separated mirror base URLs (default none),
#                               e.g. "http://azure.archive.ubuntu.com/ubuntu"
#   APT_PREFETCH_JOBS           parallel downloads (default 6)
#   APT_PREFETCH_ROUND_TIMEOUT  seconds per source (default 900)
set -euo pipefail

log() { echo "[apt_prefetch $(date -u +%H:%M:%S)] $*"; }
[ "$#" -gt 0 ] || { echo "usage: $0 PKG..." >&2; exit 2; }

JOBS="${APT_PREFETCH_JOBS:-6}"
ROUND_TIMEOUT="${APT_PREFETCH_ROUND_TIMEOUT:-900}"
read -r -a MIRRORS <<< "${UBUNTU_POOL_MIRRORS:-}"
HELPER=/usr/lib/apt/apt-helper
SNAPSHOT_POOL_RE='^https?://snapshot\.ubuntu\.com/ubuntu/[0-9]{8}T[0-9]{6}Z/(pool/.+)$'
NAME_RE='^[A-Za-z0-9][A-Za-z0-9.+~%_-]*\.deb$'
SHA_RE='^SHA256:[0-9a-f]{64}$'
# Mirrors are only a shortcut: one attempt per file, short timeout.
MIRROR_OPTS=(-o Acquire::Retries=0 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20)
PROBE_FILES=5 PROBE_TIMEOUT=60  # an unreachable mirror costs at most this long

ARCHIVES=""
eval "$(apt-config shell ARCHIVES Dir::Cache::Archives/d)"
ARCHIVES="${ARCHIVES%/}"
if [ ! -x "$HELPER" ] || [ -z "$ARCHIVES" ] || [ ! -w "$ARCHIVES" ]; then
    log "skipped: needs $HELPER and a writable archive cache (${ARCHIVES:-none}); cached files unchecked (exit 3)"
    exit 3
fi
mkdir -p "$ARCHIVES/partial"
work="$(mktemp -d "$ARCHIVES/partial/prefetch.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir "$work/new" "$work/empty" "$work/empty/partial"
: > "$work/fetch.log"
# apt-helper downloads as _apt when run as root (like apt): let it write there.
if [ "$(id -u)" = 0 ] && id _apt > /dev/null 2>&1; then
    chmod 0755 "$work"
    chown _apt "$work/new"
fi

# Every file the install needs. Against an empty cache directory apt lists all
# of them, so files that are already cached get their hash checked below.
if ! apt-get install --print-uris -qq -y --no-install-recommends \
        -o Acquire::ForceHash=SHA256 -o Dir::Cache::Archives="$work/empty/" "$@" \
        > "$work/uris" 2> "$work/uris.err"; then
    log "apt-get --print-uris failed: cached files cannot be checked (exit 3, the caller purges them):"
    sed 's/^/    /' "$work/uris.err"
    exit 3
fi
# Lines: 'URI' FILE SIZE SHA256:HEX
uri=() name=() size=() sha=() ok=() unexpected=0
while read -r u n s h; do
    u="${u#\'}"
    u="${u%\'}"
    if [[ $n =~ $NAME_RE && $s =~ ^[0-9]+$ && $h =~ $SHA_RE ]]; then
        uri+=("$u") name+=("$n") size+=("$s") sha+=("${h#SHA256:}")
    else
        log "unexpected --print-uris line: $u $n $s $h"
        unexpected=1
    fi
done < <(grep "^'" "$work/uris" || true)
# A file this script cannot name cannot be hash-checked either, and apt would
# take a cached copy of the right size unchecked: fail, the caller purges.
[ "$unexpected" = 0 ] || exit 3
total=${#name[@]}
if [ "$total" -eq 0 ]; then
    log "nothing to download"
    exit 0
fi

# intact FILE INDEX: FILE has the size and SHA256 that the index names.
intact() {
    [ -f "$1" ] && [ "$(stat -c %s "$1")" = "${size[$2]}" ] \
        && [ "$(sha256sum < "$1" | cut -d' ' -f1)" = "${sha[$2]}" ]
}

cached=0
for i in "${!name[@]}"; do
    f="$ARCHIVES/${name[i]}"
    if intact "$f" "$i"; then
        ok[i]=1
        cached=$((cached + 1))
    elif [ -e "$f" ]; then
        log "removing cached ${name[i]}: size or SHA256 differs from the index"
        rm -f "$f"
    fi
done
log "$total files needed, $cached already cached and intact"

# fetch LIST JOBS SECONDS [apt option...]: download the "INDEX URI" lines of
# LIST with JOBS parallel apt-helper processes (each one connection, in
# order, hash-checked) and move every intact file into the cache. Sets got.
fetch() {
    local list=$1 jobs=$2 limit=$3 i u j n=0 pids=()
    shift 3
    for ((j = 0; j < jobs; j++)); do : > "$work/chunk.$j"; done
    while read -r i u; do
        printf '%s\0%s\0%s\0' "$u" "$work/new/${name[i]}" "SHA256:${sha[i]}" \
            >> "$work/chunk.$((n % jobs))"
        n=$((n + 1))
    done < "$list"
    for ((j = 0; j < jobs && j < n; j++)); do
        (
            mapfile -d '' -t args < "$work/chunk.$j"
            exec timeout -k 10 "$limit" "$HELPER" "$@" download-file "${args[@]}"
        ) >> "$work/fetch.log" 2>&1 &
        pids+=("$!")
    done
    for j in "${pids[@]}"; do wait "$j" || true; done
    got=0
    while read -r i u; do
        f="$work/new/${name[i]}"
        if intact "$f" "$i"; then
            mv -f "$f" "$ARCHIVES/${name[i]}"
            ok[i]=1
            got=$((got + 1))
        fi
        rm -f "$f" "$f.FAILED"
    done < "$list"
}

# report LABEL WANTED: one line per source, plus its errors other than 404.
report() {
    local n404
    n404=$(grep -c '^E: Failed to fetch .* 404 ' "$work/fetch.log" || true)
    log "$1: $got of $2 files (${n404} not found there)"
    grep '^E: Failed to fetch' "$work/fetch.log" | grep -v ' 404 ' | head -n 20 | sed 's/^/    /' || true
    : > "$work/fetch.log"
}

# 1. Mirrors, for snapshot pool files. Smallest files first; the first few
#    are a probe on one connection.
for m in "${MIRRORS[@]}"; do
    m="${m%/}"
    for i in "${!name[@]}"; do
        if [ -z "${ok[i]:-}" ] && [[ ${uri[i]} =~ $SNAPSHOT_POOL_RE ]]; then
            echo "${size[i]} $i $m/${BASH_REMATCH[1]}"
        fi
    done | sort -n -k1,1 | cut -d' ' -f2- > "$work/list"
    wanted=$(wc -l < "$work/list")
    [ "$wanted" -gt 0 ] || break
    head -n "$PROBE_FILES" "$work/list" > "$work/probe"
    tail -n +"$((PROBE_FILES + 1))" "$work/list" > "$work/rest"
    fetch "$work/probe" 1 "$PROBE_TIMEOUT" "${MIRROR_OPTS[@]}"
    if [ "$got" -eq 0 ]; then
        report "$m (probe; mirror skipped)" "$(wc -l < "$work/probe")"
        continue
    fi
    probe_got=$got
    fetch "$work/rest" "$JOBS" "$ROUND_TIMEOUT" "${MIRROR_OPTS[@]}"
    got=$((got + probe_got))
    report "$m" "$wanted"
done

# 2. What is left, from the sources apt chose (with apt's configured retries).
for i in "${!name[@]}"; do
    if [ -z "${ok[i]:-}" ]; then echo "$i ${uri[i]}"; fi
done > "$work/list"
wanted=$(wc -l < "$work/list")
if [ "$wanted" -gt 0 ]; then
    fetch "$work/list" "$JOBS" "$ROUND_TIMEOUT"
    report "apt's own sources" "$wanted"
fi

left=0
for i in "${!name[@]}"; do
    if [ -z "${ok[i]:-}" ]; then left=$((left + 1)); fi
done
log "done: $((total - left)) of $total files in the cache, intact; $left left to apt-get"
