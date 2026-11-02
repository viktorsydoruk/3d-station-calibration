#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0
"""Create and optionally push a calendar-version release tag.

Tags use the form ``vYYYY.MM.DD.N``. The revision ``N`` starts at zero for the
first release of a day and increments for every further release on that day.

The helper refuses to tag a dirty checkout or a commit that has not been pushed
to the branch upstream, creates an annotated tag, and pushes it to the selected
remote. Use ``--dry-run`` to see the tag that would be created.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

TAG_RE = re.compile(
    r"^v(?P<date>[0-9]{4}\.[0-9]{2}\.[0-9]{2})\.(?P<revision>[0-9]+)$"
)
DATE_RE = re.compile(r"^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$")


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        fail(f"git {' '.join(args)} failed: {detail}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and push a vYYYY.MM.DD.N release tag.",
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="Git remote that receives the tag (default: origin).",
    )
    parser.add_argument(
        "--date",
        help="Release date as YYYY.MM.DD (default: today, local time).",
    )
    parser.add_argument(
        "--message",
        "-m",
        help="Annotated tag message (default: 'Release <tag>').",
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Create a GPG-signed tag with 'git tag -s'.",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Do not fetch tags from the remote before choosing the revision.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Create the tag locally without pushing it.",
    )
    parser.add_argument(
        "--allow-unpushed",
        action="store_true",
        help="Allow tagging a commit that is not pushed to the branch upstream.",
    )
    parser.add_argument(
        "--allow-tagged-head",
        action="store_true",
        help="Allow another release tag on a commit that is already tagged.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run 'python -m pytest -q' before creating the tag.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the tag that would be created and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    top = git(Path.cwd(), "rev-parse", "--show-toplevel")
    repo = Path(top.stdout.strip())

    status = git(repo, "status", "--porcelain", "--untracked-files=normal").stdout.strip()
    if status:
        fail(
            "the Git working tree is not clean; commit, stash, or remove these "
            f"changes first:\n{status}"
        )

    if not args.no_fetch:
        # With --no-push the new tag is local-only, so do not prune local tags
        # that are not on the remote yet.
        fetch_args = ["fetch", "--tags", "--prune"]
        if not args.no_push:
            fetch_args.append("--prune-tags")
        git(repo, *fetch_args, args.remote)

    branch_result = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch_result.returncode != 0:
        fail("HEAD is detached; check out the release branch before tagging.")
    branch = branch_result.stdout.strip()

    if not args.allow_unpushed:
        upstream_result = git(
            repo,
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
            check=False,
        )
        if upstream_result.returncode != 0:
            fail(
                f"branch '{branch}' has no upstream; publish it with "
                f"'git push -u {args.remote} {branch}' first"
            )
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        upstream = git(repo, "rev-parse", "@{u}").stdout.strip()
        if head != upstream:
            fail(
                f"'{branch}' is not pushed to its upstream; push the commit first "
                "or pass --allow-unpushed"
            )

    if args.date:
        date_text = args.date.strip()
        if not DATE_RE.match(date_text):
            fail("--date must use the form YYYY.MM.DD")
        try:
            dt.datetime.strptime(date_text, "%Y.%m.%d")
        except ValueError as exc:
            fail(f"invalid --date value: {exc}")
    else:
        date_text = dt.date.today().strftime("%Y.%m.%d")

    revisions: list[int] = []
    for tag in git(repo, "tag", "--list", f"v{date_text}.*").stdout.splitlines():
        match = TAG_RE.match(tag.strip())
        if match and match.group("date") == date_text:
            revisions.append(int(match.group("revision")))

    revision = max(revisions, default=-1) + 1
    tag = f"v{date_text}.{revision}"

    head_tags = [
        item.strip()
        for item in git(repo, "tag", "--points-at", "HEAD").stdout.splitlines()
        if item.strip()
    ]
    if head_tags and not args.allow_tagged_head:
        fail(
            "HEAD is already tagged ("
            + ", ".join(head_tags)
            + "); create a new commit or pass --allow-tagged-head"
        )

    tag_exists = git(
        repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}", check=False
    )
    if tag_exists.returncode == 0:
        fail(f"tag '{tag}' already exists")

    if args.dry_run:
        print(f"Would create annotated tag {tag} on {branch}.")
        if not args.no_push:
            print(f"Would push {tag} to {args.remote}.")
        return 0

    if args.run_tests:
        tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo)
        if tests.returncode != 0:
            fail("tests failed; the tag was not created")

    message = args.message or f"Release {tag}"
    tag_args = ["tag", "-s" if args.sign else "-a", tag, "-m", message]
    git(repo, *tag_args)

    if not args.no_push:
        git(repo, "push", args.remote, tag)

    print(f"Created annotated tag {tag} on {branch}.")
    if not args.no_push:
        print(f"Pushed {tag} to {args.remote}.")
    print(
        "Builds from this commit now report the release version; commits after "
        "the tag receive a .devN suffix."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
