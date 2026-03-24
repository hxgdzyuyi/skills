#!/usr/bin/env bash
# fetch_contributors.sh
# Usage: bash fetch_contributors.sh OWNER REPO
# Output (all files under a unique temp directory):
#   <WORK_DIR>/gh_users_all.tsv  — raw user data, one user per line (tab-separated)
#   <WORK_DIR>/chunk_*           — split files, up to 200 lines each
# The last line of stdout is the WORK_DIR path — callers should capture it.

set -euo pipefail

OWNER="${1:?Usage: fetch_contributors.sh OWNER REPO}"
REPO="${2:?Usage: fetch_contributors.sh OWNER REPO}"
WORK_DIR="$(mktemp -d /tmp/gh_work_XXXXXXXX)"
OUT_TSV="${WORK_DIR}/gh_users_all.tsv"
CHUNK_PREFIX="${WORK_DIR}/chunk_"
CHUNK_SIZE=200

echo "[fetch] Fetching mentionable users for ${OWNER}/${REPO} ..."

# ── 2. Pull all pages via GraphQL ─────────────────────────────────────────────
gh api graphql --paginate \
  -F owner="$OWNER" \
  -F repo="$REPO" \
  -F first=100 \
  -f query='
    query GetRepositoryUsers(
      $owner: String!
      $repo: String!
      $first: Int!
      $endCursor: String
    ) {
      repository(owner: $owner, name: $repo) {
        mentionableUsers(first: $first, after: $endCursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            name
            login
            location
            url
            websiteUrl
          }
        }
      }
    }' \
  --jq '.data.repository.mentionableUsers.nodes[]
        | [ (.name // ""), .login, (.location // ""), .url, (.websiteUrl // "") ]
        | @tsv' \
  >> "$OUT_TSV"

TOTAL=$(wc -l < "$OUT_TSV" | tr -d ' ')
echo "[fetch] Done. Total users fetched: ${TOTAL}"

# ── 3. Create lightweight TSV (only fields needed for LLM judgment) ───────────
LIGHT_TSV="${WORK_DIR}/gh_users_light.tsv"
cut -f1,2,3 "$OUT_TSV" > "$LIGHT_TSV"

# ── 4. Split lightweight TSV into chunks ─────────────────────────────────────
if [[ "$TOTAL" -eq 0 ]]; then
  echo "[fetch] No users found. Nothing to split."
  exit 0
fi

split -l "$CHUNK_SIZE" "$LIGHT_TSV" "$CHUNK_PREFIX"

CHUNK_COUNT=$(ls "${CHUNK_PREFIX}"* 2>/dev/null | wc -l | tr -d ' ')
echo "[fetch] Split into ${CHUNK_COUNT} chunk(s) (max ${CHUNK_SIZE} lines each):"
ls -1 "${CHUNK_PREFIX}"*

# ── Last line: print WORK_DIR so the caller can capture it ────────────────────
echo "WORK_DIR=${WORK_DIR}"
