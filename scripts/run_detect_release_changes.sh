#!/bin/bash
# Installs dependencies for detect_release_changes.py on a bare RHEL-based container.
# Requires: microdnf (provided by ubi-micro / ubi-minimal base images)

set -euo pipefail

WORKDIR=$(mktemp -d)
mkdir -p $WORKDIR
cd $WORKDIR

microdnf install -y git python3
microdnf clean all

SCRIPT_DIR="$(dirname "$0")"
CHANGED_JSON="$(python3 "${SCRIPT_DIR}/detect_release_changes.py")"

if [ -z "$CHANGED_JSON" ] || [ "$CHANGED_JSON" = "[]" ]; then
  echo "No release changes detected."
  exit 0
fi

# Extract fields from the first changed entry
read_field() {
  python3 -c "import json,sys; data=json.loads(sys.argv[1]); print(data[0].get('$1','') if data else '')" "$CHANGED_JSON"
}

read_nested_field() {
  python3 -c "import json,sys; data=json.loads(sys.argv[1]); print(data[0].get('$1',{}).get('$2','') if data else '')" "$CHANGED_JSON"
}

export REPO_URL="$(read_field repo_url)"
export RELEASE="$(read_field release)"
export CODERIO_ORG="$(read_nested_field coderio org)"
export CODERIO_PROJECT="$(read_nested_field coderio project)"
export CODERIO_PIPELINE="$(read_nested_field coderio pipeline)"

echo "REPO_URL=${REPO_URL}"
echo "RELEASE=${RELEASE}"
echo "CODERIO_ORG=${CODERIO_ORG}"
echo "CODERIO_PROJECT=${CODERIO_PROJECT}"
echo "CODERIO_PIPELINE=${CODERIO_PIPELINE}"

# ---------------------------------------------------------------------------
# Harness pipeline execution
# Required environment variables:
#   HARNESS_ACCOUNT_ID   - Harness account identifier
#   HARNESS_API_KEY      - Harness API key (x-api-key)
# Optional:
#   HARNESS_BASE_URL     - defaults to https://app.harness.io
#   POLL_INTERVAL        - seconds between status checks (default: 30)
#   PIPELINE_TIMEOUT     - seconds before giving up (default: 3600)
# ---------------------------------------------------------------------------

HARNESS_BASE_URL="${HARNESS_BASE_URL:-https://app.harness.io}"
POLL_INTERVAL="${POLL_INTERVAL:-30}"
PIPELINE_TIMEOUT="${PIPELINE_TIMEOUT:-3600}"

if [ -z "${HARNESS_ACCOUNT_ID:-}" ]; then
  echo "ERROR: HARNESS_ACCOUNT_ID is not set." >&2
  exit 1
fi
if [ -z "${HARNESS_API_KEY:-}" ]; then
  echo "ERROR: HARNESS_API_KEY is not set." >&2
  exit 1
fi

# Trigger the pipeline
echo ""
echo "Triggering pipeline '${CODERIO_PIPELINE}' in org '${CODERIO_ORG}' / project '${CODERIO_PROJECT}'..."

TRIGGER_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  "${HARNESS_BASE_URL}/pipeline/api/pipeline/execute/${CODERIO_PIPELINE}?accountIdentifier=${HARNESS_ACCOUNT_ID}&orgIdentifier=${CODERIO_ORG}&projectIdentifier=${CODERIO_PROJECT}" \
  -H "x-api-key: ${HARNESS_API_KEY}" \
  -H "Content-Type: application/yaml" \
  --data-binary '')

HTTP_CODE=$(echo "$TRIGGER_RESPONSE" | tail -n1)
TRIGGER_BODY=$(echo "$TRIGGER_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -lt 200 ] || [ "$HTTP_CODE" -ge 300 ]; then
  echo "ERROR: Failed to trigger pipeline (HTTP ${HTTP_CODE}):" >&2
  echo "$TRIGGER_BODY" >&2
  exit 1
fi

PLAN_EXECUTION_ID=$(python3 -c "
import json, sys
body = json.loads(sys.argv[1])
print(body.get('data', {}).get('planExecution', {}).get('uuid', ''))
" "$TRIGGER_BODY")

if [ -z "$PLAN_EXECUTION_ID" ]; then
  echo "ERROR: Could not extract planExecutionId from response:" >&2
  echo "$TRIGGER_BODY" >&2
  exit 1
fi

echo "Pipeline triggered. planExecutionId: ${PLAN_EXECUTION_ID}"

# Poll until the pipeline reaches a terminal state
ELAPSED=0
while [ "$ELAPSED" -lt "$PIPELINE_TIMEOUT" ]; do
  STATUS_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X GET \
    "${HARNESS_BASE_URL}/pipeline/api/pipelines/execution/${PLAN_EXECUTION_ID}" \
    -H "x-api-key: ${HARNESS_API_KEY}" \
    --get \
    --data-urlencode "accountIdentifier=${HARNESS_ACCOUNT_ID}" \
    --data-urlencode "orgIdentifier=${CODERIO_ORG}" \
    --data-urlencode "projectIdentifier=${CODERIO_PROJECT}")

  HTTP_CODE=$(echo "$STATUS_RESPONSE" | tail -n1)
  STATUS_BODY=$(echo "$STATUS_RESPONSE" | head -n-1)

  if [ "$HTTP_CODE" -lt 200 ] || [ "$HTTP_CODE" -ge 300 ]; then
    echo "WARNING: Status check returned HTTP ${HTTP_CODE}; will retry..." >&2
  else
    STATUS=$(python3 -c "
import json, sys
body = json.loads(sys.argv[1])
print(body.get('data', {}).get('pipelineExecutionSummary', {}).get('status', ''))
" "$STATUS_BODY")

    echo "[${ELAPSED}s] Pipeline status: ${STATUS}"

    case "$STATUS" in
      Success)
        echo "Pipeline completed successfully."
        exit 0
        ;;
      Failed|Aborted|Expired|ApprovalRejected)
        echo "ERROR: Pipeline ended with status '${STATUS}'." >&2
        exit 1
        ;;
    esac
  fi

  sleep "$POLL_INTERVAL"
  ELAPSED=$(( ELAPSED + POLL_INTERVAL ))
done

echo "ERROR: Timed out after ${PIPELINE_TIMEOUT}s waiting for pipeline to complete." >&2
exit 1
