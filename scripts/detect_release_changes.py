#!/usr/bin/env python3
"""
Detects changes to the 'release' field in repositories.yaml files by comparing
HEAD against HEAD~1 (the most recent commit against the previous commit).
Outputs JSON objects from HEAD where 'release' has changed, each annotated with
an 'environment' field derived from the file's directory name.
"""

import json
import os
import subprocess
import sys

import yaml


def run_git(args):
    result = subprocess.run(["git"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def get_repo_root():
    root = run_git(["rev-parse", "--show-toplevel"])
    return root.strip() if root else os.getcwd()


def get_changed_repos_files():
    """Return repositories.yaml paths that differ between HEAD~1 and HEAD."""
    output = run_git(["diff", "--name-only", "HEAD~1", "HEAD"])
    if not output:
        return []
    return [
        f.strip()
        for f in output.splitlines()
        if f.strip().endswith("repositories.yaml")
    ]


def get_file_at_ref(path, ref):
    """Return file content at a git ref, or None if it doesn't exist there."""
    return run_git(["show", f"{ref}:{path}"])


def extract_env_name(path):
    """
    Extract the environment name from a path of the form
    'environments/<env-name>/repositories.yaml'.
    Falls back to the immediate parent directory name.
    """
    parts = path.replace("\\", "/").split("/")
    return parts[-2] if len(parts) >= 2 else "unknown"


def parse_repos(content):
    """Parse YAML content into a list of repository entries."""
    if not content:
        return []
    data = yaml.safe_load(content)
    return data if isinstance(data, list) else []


def find_release_changes(old_content, new_content, env_name):
    """
    Return entries from new_content whose 'release' field differs from old_content.
    Entries are matched by 'repo_url'. New entries (not in old) are included
    if they carry a 'release' field. Each returned entry includes 'environment'.
    """
    old_list = parse_repos(old_content)
    new_list = parse_repos(new_content)

    old_by_url = {e["repo_url"]: e for e in old_list if "repo_url" in e}

    changed = []
    for entry in new_list:
        repo_url = entry.get("repo_url")
        enriched = dict(entry, environment=env_name)
        if repo_url and repo_url in old_by_url:
            if entry.get("release") != old_by_url[repo_url].get("release"):
                changed.append(enriched)
        else:
            # New entry — include if it has a release field
            if "release" in entry:
                changed.append(enriched)

    return changed


def main():
    changed_files = get_changed_repos_files()
    if not changed_files:
        print("[]")
        sys.exit(0)

    all_changed = []
    for path in changed_files:
        env_name = extract_env_name(path)

        # new = HEAD (latest commit); old = HEAD~1 (previous commit)
        new_content = get_file_at_ref(path, "HEAD")
        if new_content is None:
            # File was deleted in HEAD — nothing to deploy
            continue

        old_content = get_file_at_ref(path, "HEAD~1")

        try:
            changed = find_release_changes(old_content, new_content, env_name)
            all_changed.extend(changed)
        except yaml.YAMLError as e:
            print(f"Error parsing {path}: {e}", file=sys.stderr)
            sys.exit(1)

    print(json.dumps(all_changed, indent=2))


if __name__ == "__main__":
    main()
