#!/usr/bin/env python3
import argparse, hashlib, json, os, re, shutil, subprocess, tarfile, tempfile
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")

def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, env={**os.environ, "GIT_CONFIG_NOSYSTEM":"1"})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url", required=True); p.add_argument("--revision", required=True)
    p.add_argument("--output", required=True); p.add_argument("--submodules", action="store_true")
    a=p.parse_args()
    if not SHA.fullmatch(a.revision): p.error("revision must be a full 40-character commit")
    out=Path(a.output); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        repo=Path(d)/"repo"
        run("git","init",str(repo))
        run("git","-C",str(repo),"remote","add","origin",a.url)
        run("git","-C",str(repo),"fetch","--depth=1","origin",a.revision)
        run("git","-C",str(repo),"checkout","--detach","FETCH_HEAD")
        actual=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
        if actual != a.revision: raise SystemExit(f"revision mismatch: {actual}")
        if a.submodules: run("git","-C",str(repo),"submodule","update","--init","--recursive","--depth=1")
        shutil.rmtree(repo/".git")
        archive=out/"source.tar"
        with tarfile.open(archive,"w",format=tarfile.PAX_FORMAT) as tf:
            for path in sorted(repo.rglob("*"),key=lambda x:x.relative_to(repo).as_posix()):
                info=tf.gettarinfo(str(path),path.relative_to(repo).as_posix())
                info.uid=info.gid=0; info.uname=info.gname=""; info.mtime=1
                if path.is_file():
                    with path.open("rb") as f: tf.addfile(info,f)
                else: tf.addfile(info)
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        nar=subprocess.check_output(["nix","--extra-experimental-features","nix-command","hash","path","--type","sha256",str(repo)],text=True).strip()
        (out/"source.json").write_text(json.dumps({"url":a.url,"revision":actual,"sha256":digest,"narHash":nar,"size":archive.stat().st_size},sort_keys=True,indent=2)+"\n")
if __name__=="__main__": main()
