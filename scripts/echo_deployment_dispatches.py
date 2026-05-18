#!/usr/bin/env python3
"""
Reads the changed repository list produced by detect_release_changes.py and
prints the deployment pipeline details that would be triggered for each entry.
"""

import json
import sys

import yaml


def main():
    with open("/tmp/changed_repos.json") as f:
        changed = json.load(f)

    if not changed:
        print("No release changes detected. Nothing to dispatch.")
        sys.exit(0)

    with open("_meta/repository_bindings.yaml") as f:
        bindings = yaml.safe_load(f)

    print("=== Deployment dispatches ===")
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

        print(f"[DRY RUN] Would execute deployment pipeline:")
        print(f"  Pipeline:           {pipeline}")
        print(f"  Organization:       {org}")
        print(f"  Project:            {project}")
        print(f"  RepoUrl:            {repo_url}")
        print(f"  ReleaseTag:         {release}")
        print(f"  EnvironmentName:    {env_name}")
        print(f"  EnvironmentRef:     {environment_ref}")
        print(f"  InfrastructureRef:  {infrastructure_ref}")
        print(f"  GitHubConnectorRef: {github_connector_ref}")
        print()


if __name__ == "__main__":
    main()
