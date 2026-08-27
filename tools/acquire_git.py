#!/usr/bin/env python3
import argparse, hashlib, io, json, os, random, re, shutil, subprocess, tarfile, tempfile, time, urllib.request
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")

# Read-only mirrors are used only as alternate transports. Every acquisition
# still verifies the immutable commit requested by the BuildStream source lock.
MIRRORS = {
    "https://gcc.gnu.org/git/gcc.git": "https://github.com/gcc-mirror/gcc.git",
    "https://sourceware.org/git/binutils-gdb.git": "https://gitlab.com/x86-binutils/binutils-gdb.git",
    "https://sourceware.org/git/bzip2.git": "https://gitlab.com/bzip2/bzip2.git",
    "https://sourceware.org/git/glibc.git": "https://gitlab.com/x86-glibc/glibc.git",
    "https://sourceware.org/git/dwz.git": "https://git.sr.ht/~sourceware/dwz",
    "https://sourceware.org/git/valgrind.git": "https://git.sr.ht/~sourceware/valgrind",
    "https://git.linuxtv.org/v4l-utils.git": "https://github.com/gjasny/v4l-utils.git",
}
ARCHIVE_FIRST = {"https://git.linuxtv.org/v4l-utils.git"}

def download_github_archive(url, revision, attempts=7):
    match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?", url)
    if match is None:
        return None
    archive_url = (
        f"https://codeload.github.com/{match.group(1)}/{match.group(2)}"
        f"/tar.gz/{revision}"
    )
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                archive_url, headers={"User-Agent": "bst2nix/0.1"}
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(min(60, 2 ** attempt) + random.uniform(0, 1))

def git_environment(url):
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
    token = env.get("GITHUB_TOKEN")
    if token and url.startswith("https://github.com/"):
        # Supply credentials through Git's protected process environment. Never
        # place the token in argv, generated targets, action metadata, or logs.
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {token}",
        })
    return env

def run(*args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, check=True, env=env or os.environ)

def fetch_from(repo, url, revision, attempts=7):
    env = git_environment(url)
    run("git", "-C", str(repo), "remote", "set-url", "origin", url, env=env)
    for attempt in range(attempts):
        result = subprocess.run(
            # A shared repository may acquire several revisions in one action.
            # Do not use shallow fetches: repeated depth updates rewrite
            # .git/shallow and can race Git's background object maintenance.
            # Fetch complete objects as well: a partial clone defers blobs until
            # checkout, moving network failures outside this retry loop.
            ["git", "-C", str(repo), "fetch", "origin", revision],
            env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            return
        if (
            url.startswith("https://github.com/")
            and "could not read Username" in result.stderr
            and "GIT_CONFIG_VALUE_0" in env
        ):
            # An expired or scope-restricted token must not make public
            # repositories less available than anonymous GitHub access.
            env = {
                key: value
                for key, value in env.items()
                if key not in {
                    "GIT_CONFIG_COUNT",
                    "GIT_CONFIG_KEY_0",
                    "GIT_CONFIG_VALUE_0",
                }
            }
            continue
        transient = any(marker in result.stderr for marker in (
            "429", "500", "502", "503", "504", "timed out", "Connection reset",
            "remote end hung up", "Could not resolve host", "early EOF",
            "unexpected disconnect", "reset by server",
        ))
        if "unadvertised object" in result.stderr:
            # Some servers reject want-by-SHA even for reachable commits.
            # Fetch advertised refs with blob filtering, then resolve the
            # pinned commit locally.
            fallback = subprocess.run(
                ["git", "-C", str(repo), "fetch", "--filter=blob:none",
                 "origin", "+refs/heads/*:refs/remotes/origin/*",
                 "+refs/tags/*:refs/tags/*"],
                env=env, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if fallback.returncode == 0:
                present = subprocess.run(
                    ["git", "-C", str(repo), "cat-file", "-e",
                     f"{revision}^{{commit}}"], env=env,
                )
                if present.returncode == 0:
                    return
            print(fallback.stderr, end="", file=os.sys.stderr)
            raise subprocess.CalledProcessError(fallback.returncode, fallback.args)
        if "dumb http transport does not support shallow capabilities" in result.stderr:
            # Static/dumb HTTP servers cannot negotiate shallow or filtered
            # fetches. Fall back to advertised refs without those capabilities.
            fallback = subprocess.run(
                ["git", "-C", str(repo), "fetch", "origin",
                 "+refs/heads/*:refs/remotes/origin/*",
                 "+refs/tags/*:refs/tags/*"],
                env=env, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if fallback.returncode == 0:
                present = subprocess.run(
                    ["git", "-C", str(repo), "cat-file", "-e",
                     f"{revision}^{{commit}}"], env=env,
                )
                if present.returncode == 0:
                    return
            print(fallback.stderr, end="", file=os.sys.stderr)
            raise subprocess.CalledProcessError(fallback.returncode, fallback.args)
        if not transient or attempt + 1 == attempts:
            print(result.stderr, end="", file=os.sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, result.args)
        delay = min(60, 2 ** attempt) + random.uniform(0, 1)
        print(f"transient Git failure; retrying in {delay:.1f}s "
              f"({attempt + 1}/{attempts})", file=os.sys.stderr)
        time.sleep(delay)

def fetch_with_retry(repo, url, revision):
    candidates = [MIRRORS[url], url] if url in MIRRORS else [url]
    last_error = None
    for candidate in candidates:
        try:
            fetch_from(repo, candidate, revision)
            return candidate
        except subprocess.CalledProcessError as error:
            last_error = error
            if candidate != candidates[-1]:
                print(
                    f"Git mirror {candidate} failed; trying canonical URL",
                    file=os.sys.stderr,
                )
    raise last_error

def write_materialization(clean, output, url, revision):
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "source.tar"
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as tf:
        paths = [
            path for path in clean.rglob("*")
            if ".git" not in path.relative_to(clean).parts
        ]
        for path in sorted(paths, key=lambda x: x.relative_to(clean).as_posix()):
            info = tf.gettarinfo(str(path), path.relative_to(clean).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 1
            if path.is_file():
                with path.open("rb") as source_file:
                    tf.addfile(info, source_file)
            else:
                tf.addfile(info)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    nar = subprocess.check_output(
        ["nix", "--extra-experimental-features", "nix-command", "hash", "path",
         "--type", "sha256", str(clean)],
        text=True,
    ).strip()
    (output / "source.json").write_text(json.dumps({
        "url": url,
        "revision": revision,
        "sha256": digest,
        "narHash": nar,
        "size": archive.stat().st_size,
    }, sort_keys=True, indent=2) + "\n")

def materialize(repo, output, url, revision, submodules, env, temporary):
    run("git", "-C", str(repo), "checkout", "--force", "--detach", revision, env=env)
    run("git", "-C", str(repo), "clean", "-ffd", env=env)
    actual = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != revision:
        raise SystemExit(f"revision mismatch: {actual}")
    if submodules:
        run(
            "git", "-C", str(repo), "submodule", "update", "--init",
            "--recursive", "--depth=1", env=env,
        )
    clean = temporary / f"source-{output.name}"
    shutil.copytree(
        repo,
        clean,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git"),
    )
    write_materialization(clean, output, url, actual)

def materialize_github(data, output, url, revision, temporary):
    extract_root = temporary / f"archive-{output.name}"
    extract_root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        archive.extractall(extract_root, filter="data")
    roots = list(extract_root.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise RuntimeError("GitHub archive does not have one root directory")
    write_materialization(roots[0], output, url, revision)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--revision")
    p.add_argument("--source", action="append", default=[])
    p.add_argument("--output", required=True); p.add_argument("--submodules", action="store_true")
    a=p.parse_args()
    if bool(a.revision) == bool(a.source):
        p.error("specify either --revision or one or more --source ID=REVISION")
    requested = []
    if a.revision:
        requested.append((None, a.revision))
    for value in a.source:
        source_id, separator, revision = value.partition("=")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", source_id):
            p.error("--source must be ID=REVISION with a 64-character source ID")
        requested.append((source_id, revision))
    if any(not SHA.fullmatch(revision) for _, revision in requested):
        p.error("revision must be a full 40-character commit")
    out=Path(a.output); out.mkdir(parents=True, exist_ok=True)
    # Some Git versions can leave an object maintenance process alive briefly
    # after fetch. The repository is disposable, so cleanup must not turn an
    # otherwise successful acquisition into a failed Buck action.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        repo=Path(d)/"repo"
        temporary = Path(d)
        env = git_environment(a.url)
        run("git","init",str(repo),env=env)
        run("git", "-C", str(repo), "config", "gc.auto", "0", env=env)
        run("git", "-C", str(repo), "config", "maintenance.auto", "false", env=env)
        run("git","-C",str(repo),"remote","add","origin",a.url,env=env)
        fetched_from = a.url
        archives = {}
        for source_id, revision in requested:
            if a.url in ARCHIVE_FIRST and not a.submodules:
                archives[source_id] = download_github_archive(
                    MIRRORS[a.url], revision
                )
                continue
            try:
                fetched_from = fetch_with_retry(repo, a.url, revision)
            except subprocess.CalledProcessError:
                mirror = MIRRORS.get(a.url)
                if a.submodules or a.url not in ARCHIVE_FIRST or mirror is None:
                    raise
                data = download_github_archive(mirror, revision)
                if data is None:
                    raise
                archives[source_id] = data
        # Checkout may lazily access the promisor remote for repositories
        # fetched from a mirror, so retain the transport that supplied objects.
        run(
            "git", "-C", str(repo), "remote", "set-url", "origin",
            fetched_from, env=git_environment(fetched_from),
        )
        for source_id, revision in requested:
            destination = out if source_id is None else out / source_id
            if source_id in archives:
                materialize_github(
                    archives[source_id], destination, a.url, revision, temporary
                )
            else:
                materialize(
                    repo, destination, a.url, revision, a.submodules, env, temporary
                )
if __name__=="__main__": main()
