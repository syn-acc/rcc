#!/usr/bin/env python3
"""Install RCC and its provider plugins together, or print their content digest."""

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def plugin_files(directory):
    if not stat.S_ISDIR(directory.lstat().st_mode):
        raise ValueError(f"expected a real directory at {directory}")
    for item in directory.iterdir():
        if item.name.startswith(".") or item.name == "__pycache__" or item.suffix in (".pyc", ".pyo"):
            continue
        if stat.S_ISDIR(item.lstat().st_mode):
            yield from plugin_files(item)
        else:
            yield item


def payload(root):
    # Read once so installation uses precisely the bytes that were hashed. Reject links and devices.
    files = {}
    for path in (root / "rcc", root / "rccd", *plugin_files(root / "plugins")):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            mode = os.fstat(fd).st_mode
            if not stat.S_ISREG(mode):
                raise ValueError(f"expected a regular file at {path}")
            files[path.relative_to(root)] = (bool(mode & 0o111), stream.read())
    if not all(files[Path(name)][0] for name in ("rcc", "rccd")):
        raise ValueError("source rcc and rccd must be executable")
    return files


def bundle_digest(files):
    digest = hashlib.sha256(b"rcc-bundle-v1\x00")
    for path, (executable, content) in sorted(files.items(), key=lambda entry: entry[0].as_posix()):
        name = path.as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(bytes([executable]))
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def write_release(release, files):
    # Build privately on this filesystem. Only a complete tree gets the digest's name.
    with tempfile.TemporaryDirectory(prefix=".rcc-stage-", dir=release.parent) as temp:
        stage = Path(temp)
        (stage / "plugins").mkdir(parents=True)
        for relative, (executable, content) in files.items():
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o555 if executable else 0o444)
        for directory, _, _ in os.walk(stage, topdown=False):
            os.chmod(directory, 0o555)
        stage.rename(release)


def verify_release(release, digest):
    if not stat.S_ISDIR(release.lstat().st_mode):
        raise ValueError(f"expected a release directory at {release}")
    if {p.name for p in release.iterdir()} != {"rcc", "rccd", "plugins"}:
        raise ValueError(f"unexpected entries in release {release}")
    for directory, dirs, files in os.walk(release):
        for name in [".", *dirs, *files]:
            mode = (Path(directory) / name).lstat().st_mode
            if stat.S_ISLNK(mode) or mode & 0o222:
                raise ValueError(f"release is mutable at {Path(directory) / name}")
    if bundle_digest(payload(release)) != digest:
        raise ValueError(f"existing release failed digest verification at {release}")


def install(target, digest, files):
    # Resolve parents only: the final component is the link to switch, not a path to overwrite.
    target = Path(os.path.abspath(target))
    prefix = target.parent.parent if target.parent.name == "bin" else target.parent
    versions = prefix / "lib" / "rcc"
    versions.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    release = versions / digest
    fd = os.open(versions, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if os.path.lexists(release):
            verify_release(release, digest)
        else:
            write_release(release, files)
        with tempfile.TemporaryDirectory(prefix=".rcc-switch-", dir=target.parent) as temp:
            daemon = target.with_name(target.name + "d")
            if os.path.lexists(daemon) and not (daemon.is_symlink() and
                    daemon.resolve().name == "rccd" and daemon.resolve().parent.parent == versions.resolve()):
                raise ValueError(f"an unrelated file occupies {daemon}")
            if target.is_dir():
                raise ValueError(f"expected a client executable at {target}")
            for name, dest in (("rccd", daemon), ("rcc", target)):
                link = Path(temp) / name
                link.symlink_to(os.path.relpath(release.resolve() / name, target.parent.resolve()))
                os.replace(link, dest)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("/usr/local/bin/rcc"))
    parser.add_argument("--digest", action="store_true", help="print the bundle's SHA-256 and exit")
    parser.add_argument("--expect-digest", metavar="HASH", help="require the given bundle SHA-256")
    args = parser.parse_args()
    try:
        files = payload(Path(__file__).resolve().parent)
        digest = bundle_digest(files)
        if args.expect_digest is not None:
            expected = args.expect_digest.lower()
            if not re.fullmatch("[0-9a-f]{64}", expected) or expected != digest:
                raise ValueError(f"RCC bundle digest mismatch (computed {digest})")
        if args.digest:
            print(digest)
        else:
            install(args.target, digest, files)
            print(f"Installed RCC {digest} at {args.target}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"rcc install: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
