#!/usr/bin/env python3
"""Fail if a source tree or delivery ZIP contains transient test caches."""
from __future__ import print_function

import argparse
import os
import sys
import zipfile


BAD_DIRS = {"__pycache__", ".pytest_cache"}


def is_bad_path(name):
    normalized = name.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    return normalized.endswith(".pyc") or any(part in BAD_DIRS for part in parts)


def scan_root(root):
    bad = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for dirname in list(dirnames):
            rel = os.path.normpath(os.path.join(rel_dir, dirname))
            if is_bad_path(rel):
                bad.append(rel)
        for filename in filenames:
            rel = os.path.normpath(os.path.join(rel_dir, filename))
            if is_bad_path(rel):
                bad.append(rel)
    return sorted(set(bad))


def scan_zip(path):
    with zipfile.ZipFile(path, "r") as archive:
        return sorted(name for name in archive.namelist() if is_bad_path(name))


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--root")
    group.add_argument("--zip")
    args = parser.parse_args()

    bad = scan_root(args.root) if args.root else scan_zip(args.zip)
    if bad:
        print("PACKAGE_HYGIENE=FAIL")
        for item in bad:
            print(item)
        return 1
    print("PACKAGE_HYGIENE=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
