#!/bin/bash
# Installs dependencies for detect_release_changes.py on a bare RHEL-based container.
# Requires: microdnf (provided by ubi-micro / ubi-minimal base images)

set -euo pipefail

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
