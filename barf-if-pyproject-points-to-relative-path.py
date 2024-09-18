#!/usr/bin/env python3
import os
import pathlib
import sys

# requires python 3.11, but this only runs on my laptop, and I am up to date there, so it should be fine
import tomllib

__here__ = pathlib.Path(__file__).parent.resolve()
pyproject_fn = __here__ / "pyproject.toml"

PRE_COMMIT_REMOTE_BRANCH = os.environ.get("PRE_COMMIT_REMOTE_BRANCH")

if PRE_COMMIT_REMOTE_BRANCH != "refs/heads/main":
    print("You're not pushing to main, so anything goes.  Have fun")
    sys.exit(0)

with open(pyproject_fn, "rb") as inf:
    pyproject_data = tomllib.load(inf)

bridge = pyproject_data["tool"]["poetry"]["dependencies"]["bridge"]

if "path" in bridge:
    print(f"Looks like the library is referred to by a relative path: {bridge=}")
    sys.exit(1)
