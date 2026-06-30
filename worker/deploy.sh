#!/bin/bash
# Deploy the support script Cloudflare Worker.
#
# Default target is staging. Production deploys require both:
#   ./worker/deploy.sh --production
#   CONFIRM_PRODUCTION_DEPLOY=support.gal.run
#
# Prerequisites: gcloud Secret Manager access or CLOUDFLARE_API_TOKEN.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER_DIR="$REPO_ROOT/worker"
ENVIRONMENT="staging"
DRY_RUN="false"
REMOTE_SUPPORT_GCP_PROJECT_DEFAULT="stratus-scheduler-systems"

usage() {
  cat <<'EOF'
Usage:
  ./worker/deploy.sh [--staging|--production] [--dry-run]

Defaults:
  --staging

Environment:
  REMOTE_SUPPORT_GCP_PROJECT      GCP project for Secret Manager.
  CLOUDFLARE_API_TOKEN            Optional override; otherwise read from Secret Manager.
  CLOUDFLARE_API_TOKEN_SECRET     Optional Secret Manager name override.
  CLOUDFLARE_ACCOUNT_ID           Optional override; otherwise read from Secret Manager.
  CLOUDFLARE_ACCOUNT_ID_SECRET    Optional Secret Manager name override.
  SUPPORT_ARTIFACT_VERSION        Defaults to current git short SHA.
  SUPPORT_BASE_URL                Defaults from selected environment.
  CONFIRM_PRODUCTION_DEPLOY       Must equal support.gal.run for --production.

Custom domains:
  staging     support-staging.gal.run
  production  support.gal.run

Default GCP secrets:
  REMOTE_SUPPORT_STAGING_CLOUDFLARE_API_TOKEN
  REMOTE_SUPPORT_PRODUCTION_CLOUDFLARE_API_TOKEN
  REMOTE_SUPPORT_CLOUDFLARE_ACCOUNT_ID
EOF
}

resolve_gcp_project() {
  if [[ -n "${REMOTE_SUPPORT_GCP_PROJECT:-}" ]]; then
    printf '%s\n' "$REMOTE_SUPPORT_GCP_PROJECT"
    return 0
  fi
  if [[ -n "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
    printf '%s\n' "$GOOGLE_CLOUD_PROJECT"
    return 0
  fi
  if [[ -n "${GCLOUD_PROJECT:-}" ]]; then
    printf '%s\n' "$GCLOUD_PROJECT"
    return 0
  fi
  if command -v gcloud >/dev/null 2>&1; then
    local configured
    configured="$(gcloud config get-value project 2>/dev/null || true)"
    if [[ -n "$configured" && "$configured" != "(unset)" ]]; then
      printf '%s\n' "$configured"
      return 0
    fi
  fi
  printf '%s\n' "$REMOTE_SUPPORT_GCP_PROJECT_DEFAULT"
}

read_gcp_secret() {
  local secret_id="$1"
  local project
  project="$(resolve_gcp_project)"
  if ! command -v gcloud >/dev/null 2>&1; then
    return 1
  fi
  gcloud secrets versions access latest --project "$project" --secret "$secret_id" 2>/dev/null
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staging)
      ENVIRONMENT="staging"
      shift
      ;;
    --production)
      ENVIRONMENT="production"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$ENVIRONMENT" == "production" ]]; then
  WORKER_NAME="support-scripts"
  DOMAIN="support.gal.run"
  DEFAULT_BASE_URL="https://support.gal.run"
  if [[ "${CONFIRM_PRODUCTION_DEPLOY:-}" != "support.gal.run" ]]; then
    echo "Refusing production deploy without CONFIRM_PRODUCTION_DEPLOY=support.gal.run" >&2
    exit 2
  fi
else
  WORKER_NAME="support-scripts-staging"
  DOMAIN="support-staging.gal.run"
  DEFAULT_BASE_URL="https://support-staging.gal.run"
fi

if [[ "$ENVIRONMENT" == "production" ]]; then
  DEFAULT_CLOUDFLARE_TOKEN_SECRET="REMOTE_SUPPORT_PRODUCTION_CLOUDFLARE_API_TOKEN"
else
  DEFAULT_CLOUDFLARE_TOKEN_SECRET="REMOTE_SUPPORT_STAGING_CLOUDFLARE_API_TOKEN"
fi

if [[ -z "${SUPPORT_ARTIFACT_VERSION:-}" ]]; then
  SUPPORT_ARTIFACT_VERSION="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
  export SUPPORT_ARTIFACT_VERSION
fi

if [[ -z "${SUPPORT_BASE_URL:-}" ]]; then
  SUPPORT_BASE_URL="$DEFAULT_BASE_URL"
  export SUPPORT_BASE_URL
fi

if [[ "$DRY_RUN" != "true" ]]; then
  if [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
    CLOUDFLARE_ACCOUNT_ID_SECRET="${CLOUDFLARE_ACCOUNT_ID_SECRET:-REMOTE_SUPPORT_CLOUDFLARE_ACCOUNT_ID}"
    if ! CLOUDFLARE_ACCOUNT_ID="$(read_gcp_secret "$CLOUDFLARE_ACCOUNT_ID_SECRET")"; then
      echo "Refusing deploy without CLOUDFLARE_ACCOUNT_ID or GCP secret $CLOUDFLARE_ACCOUNT_ID_SECRET." >&2
      echo "Run: gcloud auth login && gcloud config set project $REMOTE_SUPPORT_GCP_PROJECT_DEFAULT" >&2
      exit 2
    fi
    export CLOUDFLARE_ACCOUNT_ID
  fi

  if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    CLOUDFLARE_API_TOKEN_SECRET="${CLOUDFLARE_API_TOKEN_SECRET:-$DEFAULT_CLOUDFLARE_TOKEN_SECRET}"
    if ! CLOUDFLARE_API_TOKEN="$(read_gcp_secret "$CLOUDFLARE_API_TOKEN_SECRET")"; then
      echo "Refusing deploy without CLOUDFLARE_API_TOKEN or GCP secret $CLOUDFLARE_API_TOKEN_SECRET." >&2
      echo "Run: gcloud auth login && gcloud config set project $REMOTE_SUPPORT_GCP_PROJECT_DEFAULT" >&2
      echo "Dry-run locally with: ./worker/deploy.sh --dry-run" >&2
      exit 2
    fi
    export CLOUDFLARE_API_TOKEN
  fi
fi

# Build the worker (embed scripts)
python3 "$WORKER_DIR/build.py"

echo "Deploy target:"
echo "  environment: $ENVIRONMENT"
echo "  worker:      $WORKER_NAME"
echo "  domain:      $DOMAIN"
echo "  base URL:    $SUPPORT_BASE_URL"
echo "  version:     $SUPPORT_ARTIFACT_VERSION"
echo ""

CMD=(
  npx --yes wrangler deploy "$WORKER_DIR/index.deploy.js"
  --name "$WORKER_NAME"
  --domain "$DOMAIN"
  --compatibility-date "2025-01-01"
)

if [[ "$DRY_RUN" == "true" ]]; then
  printf 'Dry run:'
  printf ' %q' "${CMD[@]}"
  printf '\n'
  exit 0
fi

echo "Deploying worker..."
"${CMD[@]}"

echo ""
echo "Done. Test:"
echo "  curl $SUPPORT_BASE_URL/manifest.json"
