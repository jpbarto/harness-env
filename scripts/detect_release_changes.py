#!/usr/bin/env python3
"""
Detects changes to the 'release' field in repos.json files by comparing
HEAD against HEAD~1 (the most recent commit against the previous commit).
Outputs the JSON objects from HEAD where 'release' has changed.
"""

import json
import os
import subprocess
import sys


def run_git(args):
    result = subprocess.run(["git"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def get_repo_root():
    root = run_git(["rev-parse", "--show-toplevel"])
    return root.strip() if root else os.getcwd()


def get_changed_repos_files():
    """Return repos.json paths that differ between HEAD~1 and HEAD."""
    output = run_git(["diff", "--name-only", "HEAD~1", "HEAD"])
    if not output:
        return []
    return [f.strip() for f in output.splitlines() if f.strip().endswith("repos.json")]


def get_file_at_ref(path, ref):
    """Return file content at a git ref, or None if it doesn't exist there."""
    return run_git(["show", f"{ref}:{path}"])


def read_working_tree_file(path):
    """Return the current on-disk content of a file relative to the repo root."""
    full_path = os.path.join(get_repo_root(), path)
    try:
        with open(full_path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def find_release_changes(old_content, new_content):
    """
    Return entries from new_content whose 'release' field differs from old_content.
    Entries are matched by 'repo_url'. New entries (not in old) are included
    if they carry a 'release' field.
    """
    old_list = json.loads(old_content) if old_content else []
    new_list = json.loads(new_content)

    old_by_url = {e["repo_url"]: e for e in old_list if "repo_url" in e}

    changed = []
    for entry in new_list:
        repo_url = entry.get("repo_url")
        if repo_url and repo_url in old_by_url:
            if entry.get("release") != old_by_url[repo_url].get("release"):
                changed.append(entry)
        else:
            # New entry — include if it has a release field
            if "release" in entry:
                changed.append(entry)

    return changed


def main():
    changed_files = get_changed_repos_files()
    if not changed_files:
        print("[]")
        sys.exit(0)

    all_changed = []
    for path in changed_files:
        # new = HEAD (latest commit); old = HEAD~1 (previous commit)
        new_content = get_file_at_ref(path, "HEAD")
        if new_content is None:
            # File was deleted in HEAD
            continue

        old_content = get_file_at_ref(path, "HEAD~1")

        try:
            changed = find_release_changes(old_content, new_content)
            all_changed.extend(changed)
        except json.JSONDecodeError as e:
            print(f"Error parsing {path}: {e}", file=sys.stderr)
            sys.exit(1)

    print(json.dumps(all_changed, indent=2))


if __name__ == "__main__":
    main()
