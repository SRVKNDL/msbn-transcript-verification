#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
FRONTEND_DIR="$ROOT_DIR/frontend"
INFRA_VENV="$INFRA_DIR/.venv"
JSII_CACHE="${JSII_RUNTIME_PACKAGE_CACHE:-/tmp/jsii-runtime-package-cache}"

DEFAULT_FRONTEND_BUCKET="msbn-dashboard-frontend-357621881714"
DEFAULT_CLOUDFRONT_DISTRIBUTION_ID="EWFC9ZR5VW20B"

REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-}"
REQUIRE_APPROVAL="${CDK_REQUIRE_APPROVAL:-broadening}"

RUN_TESTS=1
RUN_SYNTH=1
RUN_DIFF=0
DEPLOY_FRONTEND=0
BACKEND_REQUESTED=0
FRONTEND_ONLY=0
WAIT_FOR_INVALIDATION="${WAIT_FOR_INVALIDATION:-1}"

FRONTEND_BUCKET="${FRONTEND_BUCKET:-$DEFAULT_FRONTEND_BUCKET}"
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID:-${DISTRIBUTION_ID:-$DEFAULT_CLOUDFRONT_DISTRIBUTION_ID}}"
API_BASE="${VITE_API_BASE:-}"
COGNITO_CLIENT_ID="${VITE_COGNITO_CLIENT_ID:-}"
COGNITO_REGION="${VITE_COGNITO_REGION:-$REGION}"

declare -a REQUESTED_STACKS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy.sh all [options]
  scripts/deploy.sh backend [options]
  scripts/deploy.sh frontend [options]
  scripts/deploy.sh storage|auth|compute|api [more stacks...] [options]

Examples:
  scripts/deploy.sh all \
    --frontend-bucket msbn-dashboard-frontend-357621881714 \
    --distribution-id EWFC9ZR5VW20B

  scripts/deploy.sh api --no-tests

  scripts/deploy.sh frontend \
    --api-base https://<api-id>.execute-api.us-east-1.amazonaws.com \
    --cognito-client-id <user-pool-client-id>

Options:
  --frontend                  Deploy frontend after requested backend stacks.
  --frontend-only             Build/upload frontend only.
  --frontend-bucket NAME      S3 bucket that hosts frontend assets.
                              Default: msbn-dashboard-frontend-357621881714.
  --distribution-id ID        CloudFront distribution to invalidate.
                              Default: EWFC9ZR5VW20B.
  --api-base URL              API Gateway URL for VITE_API_BASE.
  --cognito-client-id ID      Cognito app client ID for VITE_COGNITO_CLIENT_ID.
  --cognito-region REGION     Cognito region; default is AWS region.
  --region REGION             AWS/CDK region; default us-east-1.
  --profile PROFILE           AWS profile to use.
  --require-approval VALUE    CDK require-approval value; default broadening.
  --no-tests                  Skip make test.
  --no-synth                  Skip make synth.
  --no-wait-invalidation      Do not wait for CloudFront invalidation completion.
  --diff                      Run cdk diff before deploying backend stacks.
  -h, --help                  Show this help.

Environment alternatives:
  FRONTEND_BUCKET, CLOUDFRONT_DISTRIBUTION_ID, VITE_API_BASE,
  VITE_COGNITO_CLIENT_ID, VITE_COGNITO_REGION, AWS_PROFILE, AWS_REGION.
  WAIT_FOR_INVALIDATION=0 disables CloudFront invalidation waiting.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

log() {
  echo "==> $*"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

aws_args() {
  local args=(--region "$REGION")
  if [[ -n "$PROFILE" ]]; then
    args+=(--profile "$PROFILE")
  fi
  printf '%q ' "${args[@]}"
}

run_aws() {
  local args=(--region "$REGION")
  if [[ -n "$PROFILE" ]]; then
    args+=(--profile "$PROFILE")
  fi
  aws "${args[@]}" "$@"
}

cdk_env() {
  export VIRTUAL_ENV="$INFRA_VENV"
  export PATH="$INFRA_VENV/bin:$PATH"
  export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1
  export JSII_RUNTIME_PACKAGE_CACHE="$JSII_CACHE"
}

ensure_tools() {
  have_cmd aws || die "aws CLI is required"
  have_cmd npm || die "npm is required"
  have_cmd cdk || die "AWS CDK CLI is required"
  [[ -d "$INFRA_VENV" ]] || die "infra/.venv is missing. Run: make install"
  [[ -d "$FRONTEND_DIR/node_modules" ]] || die "frontend/node_modules is missing. Run: make install"
}

stack_name() {
  case "$1" in
    storage|MsbnStorageStack) echo "MsbnStorageStack" ;;
    auth|MsbnAuthStack) echo "MsbnAuthStack" ;;
    compute|MsbnComputeStack) echo "MsbnComputeStack" ;;
    api|MsbnApiStack) echo "MsbnApiStack" ;;
    *) die "Unknown stack/component: $1" ;;
  esac
}

ordered_unique_stacks() {
  local requested=" $* "
  local ordered=(MsbnStorageStack MsbnAuthStack MsbnComputeStack MsbnApiStack)
  local stack
  for stack in "${ordered[@]}"; do
    if [[ "$requested" == *" $stack "* ]]; then
      echo "$stack"
    fi
  done
}

cf_output_contains() {
  local stack="$1"
  local key_part="$2"
  run_aws cloudformation describe-stacks \
    --stack-name "$stack" \
    --query "Stacks[0].Outputs[?contains(OutputKey, \`$key_part\`)].OutputValue | [0]" \
    --output text 2>/dev/null || true
}

infer_frontend_config() {
  if [[ -z "$API_BASE" ]]; then
    API_BASE="$(cf_output_contains MsbnApiStack ApiUrl)"
    [[ "$API_BASE" == "None" ]] && API_BASE=""
  fi

  if [[ -z "$COGNITO_CLIENT_ID" ]]; then
    COGNITO_CLIENT_ID="$(cf_output_contains MsbnAuthStack UserPoolClientId)"
    [[ "$COGNITO_CLIENT_ID" == "None" ]] && COGNITO_CLIENT_ID=""
  fi
}

validate_backend() {
  if [[ "$RUN_TESTS" -eq 1 ]]; then
    log "running tests"
    (cd "$ROOT_DIR" && JSII_RUNTIME_PACKAGE_CACHE="$JSII_CACHE" make test)
  fi

  if [[ "$RUN_SYNTH" -eq 1 ]]; then
    log "synthesizing CDK"
    (cd "$ROOT_DIR" && JSII_RUNTIME_PACKAGE_CACHE="$JSII_CACHE" make synth)
  fi
}

deploy_backend() {
  local stacks=("$@")
  [[ "${#stacks[@]}" -gt 0 ]] || return 0

  cdk_env
  if [[ "$RUN_DIFF" -eq 1 ]]; then
    log "cdk diff: ${stacks[*]}"
    (cd "$INFRA_DIR" && cdk diff "${stacks[@]}")
  fi

  local stack
  for stack in "${stacks[@]}"; do
    log "deploying $stack"
    (cd "$INFRA_DIR" && cdk deploy "$stack" --require-approval "$REQUIRE_APPROVAL")
  done
}

deploy_frontend() {
  infer_frontend_config

  [[ -n "$FRONTEND_BUCKET" ]] || die "frontend bucket is required. Pass --frontend-bucket or set FRONTEND_BUCKET."
  [[ -n "$API_BASE" ]] || die "API base URL is required. Pass --api-base or deploy MsbnApiStack first."
  [[ -n "$COGNITO_CLIENT_ID" ]] || die "Cognito client ID is required. Pass --cognito-client-id or deploy MsbnAuthStack first."

  log "building frontend"
  (
    cd "$FRONTEND_DIR"
    VITE_API_BASE="$API_BASE" \
      VITE_COGNITO_CLIENT_ID="$COGNITO_CLIENT_ID" \
      VITE_COGNITO_REGION="$COGNITO_REGION" \
      npm run build
  )

  local js_asset
  js_asset="$(grep -o 'assets/[^"]*\.js' "$FRONTEND_DIR/dist/index.html" | head -1 || true)"
  if [[ -n "$js_asset" ]]; then
    log "built frontend entry asset: $js_asset"
  fi

  log "syncing frontend/dist to s3://$FRONTEND_BUCKET/"
  run_aws s3 sync "$FRONTEND_DIR/dist/" "s3://$FRONTEND_BUCKET/" --delete

  if [[ -n "$CLOUDFRONT_DISTRIBUTION_ID" ]]; then
    log "creating CloudFront invalidation for $CLOUDFRONT_DISTRIBUTION_ID"
    local invalidation_id
    invalidation_id="$(
      run_aws cloudfront create-invalidation \
        --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
        --paths '/*' \
        --query 'Invalidation.Id' \
        --output text
    )"
    log "CloudFront invalidation created: $invalidation_id"

    if [[ "$WAIT_FOR_INVALIDATION" == "1" ]]; then
      log "waiting for CloudFront invalidation to complete"
      run_aws cloudfront wait invalidation-completed \
        --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
        --id "$invalidation_id"
      log "CloudFront invalidation completed: $invalidation_id"
    fi

    local domain_name
    domain_name="$(
      run_aws cloudfront get-distribution \
        --id "$CLOUDFRONT_DISTRIBUTION_ID" \
        --query 'Distribution.DomainName' \
        --output text 2>/dev/null || true
    )"
    if [[ -n "$domain_name" && "$domain_name" != "None" ]]; then
      log "frontend URL: https://$domain_name/"
      if [[ -n "$js_asset" ]]; then
        log "verify deployed index contains asset: curl -s https://$domain_name/index.html | grep '$js_asset'"
      fi
    fi
  else
    log "no CloudFront distribution ID provided; skipping invalidation"
  fi
}

parse_args() {
  if [[ "$#" -eq 0 ]]; then
    usage
    exit 1
  fi

  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      all)
        BACKEND_REQUESTED=1
        DEPLOY_FRONTEND=1
        REQUESTED_STACKS=(MsbnStorageStack MsbnAuthStack MsbnComputeStack MsbnApiStack)
        shift
        ;;
      backend)
        BACKEND_REQUESTED=1
        REQUESTED_STACKS=(MsbnStorageStack MsbnAuthStack MsbnComputeStack MsbnApiStack)
        shift
        ;;
      frontend)
        FRONTEND_ONLY=1
        DEPLOY_FRONTEND=1
        RUN_TESTS=0
        RUN_SYNTH=0
        shift
        ;;
      storage|auth|compute|api|MsbnStorageStack|MsbnAuthStack|MsbnComputeStack|MsbnApiStack)
        BACKEND_REQUESTED=1
        REQUESTED_STACKS+=("$(stack_name "$1")")
        shift
        ;;
      --frontend)
        DEPLOY_FRONTEND=1
        shift
        ;;
      --frontend-only)
        FRONTEND_ONLY=1
        DEPLOY_FRONTEND=1
        RUN_TESTS=0
        RUN_SYNTH=0
        shift
        ;;
      --frontend-bucket)
        FRONTEND_BUCKET="${2:-}"
        [[ -n "$FRONTEND_BUCKET" ]] || die "--frontend-bucket requires a value"
        shift 2
        ;;
      --distribution-id)
        CLOUDFRONT_DISTRIBUTION_ID="${2:-}"
        [[ -n "$CLOUDFRONT_DISTRIBUTION_ID" ]] || die "--distribution-id requires a value"
        shift 2
        ;;
      --api-base)
        API_BASE="${2:-}"
        [[ -n "$API_BASE" ]] || die "--api-base requires a value"
        shift 2
        ;;
      --cognito-client-id)
        COGNITO_CLIENT_ID="${2:-}"
        [[ -n "$COGNITO_CLIENT_ID" ]] || die "--cognito-client-id requires a value"
        shift 2
        ;;
      --cognito-region)
        COGNITO_REGION="${2:-}"
        [[ -n "$COGNITO_REGION" ]] || die "--cognito-region requires a value"
        shift 2
        ;;
      --region)
        REGION="${2:-}"
        [[ -n "$REGION" ]] || die "--region requires a value"
        COGNITO_REGION="$REGION"
        shift 2
        ;;
      --profile)
        PROFILE="${2:-}"
        [[ -n "$PROFILE" ]] || die "--profile requires a value"
        shift 2
        ;;
      --require-approval)
        REQUIRE_APPROVAL="${2:-}"
        [[ -n "$REQUIRE_APPROVAL" ]] || die "--require-approval requires a value"
        shift 2
        ;;
      --no-tests)
        RUN_TESTS=0
        shift
        ;;
      --no-synth)
        RUN_SYNTH=0
        shift
        ;;
      --no-wait-invalidation)
        WAIT_FOR_INVALIDATION=0
        shift
        ;;
      --diff)
        RUN_DIFF=1
        shift
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done
}

main() {
  parse_args "$@"
  ensure_tools

  mkdir -p "$JSII_CACHE"

  if [[ "$DEPLOY_FRONTEND" -eq 1 && -z "$FRONTEND_BUCKET" ]]; then
    die "frontend bucket is required for frontend deploys. Pass --frontend-bucket or set FRONTEND_BUCKET."
  fi

  if [[ "$FRONTEND_ONLY" -eq 1 ]]; then
    deploy_frontend
    return
  fi

  if [[ "$BACKEND_REQUESTED" -eq 1 ]]; then
    mapfile -t DEPLOY_STACKS < <(ordered_unique_stacks "${REQUESTED_STACKS[@]}")
    validate_backend
    deploy_backend "${DEPLOY_STACKS[@]}"
  fi

  if [[ "$DEPLOY_FRONTEND" -eq 1 ]]; then
    deploy_frontend
  fi
}

main "$@"
