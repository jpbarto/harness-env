#!/usr/bin/env python3
"""
Reads the changed repository list produced by detect_release_changes.py,
invokes the bound Harness pipeline via the Harness REST API for each changed
repository, then polls execution status every 60 seconds until the pipeline
succeeds or fails.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import yaml

HARNESS_BASE_URL = "https://app.harness.io"
POLL_INTERVAL_SECONDS = 60
TERMINAL_STATUSES = {"Success", "Failed", "Aborted", "Expired", "ApprovalRejected"}


def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: Required environment variable {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


def _api(method, url, api_key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {e.read().decode()}") from e


def execute_pipeline(account_id, api_key, org, project, pipeline_id, input_yaml):
    url = (
        f"{HARNESS_BASE_URL}/pipeline/api/pipeline/execute/{pipeline_id}"
        f"?accountIdentifier={account_id}&orgIdentifier={org}&projectIdentifier={project}"
    )
    return _api("POST", url, api_key, {"inputYaml": input_yaml})["data"]["planExecution"]["uuid"]


def get_execution_status(account_id, api_key, org, project, execution_id):
    url = (
        f"{HARNESS_BASE_URL}/pipeline/api/pipelines/execution/{execution_id}/summary"
        f"?accountIdentifier={account_id}&orgIdentifier={org}&projectIdentifier={project}"
    )
    return _api("GET", url, api_key)["data"]["pipelineExecutionSummary"]["status"]


def build_input_yaml(pipeline_id, repo_url, release_tag, environment_ref,
                     infrastructure_ref, github_connector_ref, environment_name):
    """Build the inputYaml string in the exact format Harness expects."""
    def var(name, value):
        return f"    - name: {name}\n      type: String\n      value: \"{value}\""

    return "\n".join([
        "pipeline:",
        f"  identifier: {pipeline_id}",
        "  variables:",
        var("RepoUrl",            repo_url),
        var("ReleaseTag",         release_tag),
        var("EnvironmentRef",     environment_ref),
        var("InfrastructureRef",  infrastructure_ref),
        var("GitHubConnectorRef", github_connector_ref),
        var("EnvironmentName",    environment_name),
    ]) + "\n"


def main():
    account_id = get_env("HARNESS_ACCOUNT_ID")
    api_key    = get_env("HARNESS_API_KEY")

    with open("/tmp/changed_repos.json") as f:
        changed = json.load(f)

    if not changed:
        print("No release changes detected. Nothing to dispatch.")
        sys.exit(0)

    with open("_meta/repository_bindings.yaml") as f:
        bindings = yaml.safe_load(f)

    overall_success = True

    for entry in changed:
        repo_url           = entry.get("repo_url", "")
        env_name           = entry.get("environment", "unknown")
        release            = entry.get("release", "unknown")
        environment_ref    = entry.get("environment_ref", "UNKNOWN")
        infrastructure_ref = entry.get("infrastructure_ref", "UNKNOWN")

        meta                 = bindings.get(repo_url, {}).get("meta", {})
        org                  = meta.get("organization", "UNKNOWN")
        project              = meta.get("project", "UNKNOWN")
        pipeline             = meta.get("deploy_pipeline", "UNKNOWN")
        github_connector_ref = meta.get("github_connector_ref", "UNKNOWN")

        print(f"Invoking deployment pipeline:")
        print(f"  Pipeline:           {pipeline}")
        print(f"  Organization:       {org}")
        print(f"  Project:            {project}")
        print(f"  RepoUrl:            {repo_url}")
        print(f"  ReleaseTag:         {release}")
        print(f"  EnvironmentName:    {env_name}")
        print(f"  EnvironmentRef:     {environment_ref}")
        print(f"  InfrastructureRef:  {infrastructure_ref}")
        print(f"  GitHubConnectorRef: {github_connector_ref}")

        input_yaml = build_input_yaml(
            pipeline_id=pipeline,
            repo_url=repo_url,
            release_tag=release,
            environment_ref=environment_ref,
            infrastructure_ref=infrastructure_ref,
            github_connector_ref=github_connector_ref,
            environment_name=env_name,
        )

        try:
            execution_id = execute_pipeline(account_id, api_key, org, project, pipeline, input_yaml)
        except Exception as e:
            print(f"  ERROR: Failed to invoke pipeline: {e}")
            overall_success = False
            continue

        print(f"  Execution ID:       {execution_id}")
        print(f"  Waiting {POLL_INTERVAL_SECONDS}s before first status check...")
        time.sleep(POLL_INTERVAL_SECONDS)

        while True:
            try:
                status = get_execution_status(account_id, api_key, org, project, execution_id)
            except Exception as e:
                print(f"  ERROR: Failed to poll execution status: {e}")
                overall_success = False
                break

            print(f"  Status: {status}")

            if status in TERMINAL_STATUSES:
                if status == "Success":
                    print(f"  Result: SUCCEEDED")
                else:
                    print(f"  Result: FAILED (status: {status})")
                    overall_success = False
                break

            print(f"  Still running — waiting {POLL_INTERVAL_SECONDS}s before next poll...")
            time.sleep(POLL_INTERVAL_SECONDS)

        print()

    if not overall_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
