"""R3.1 mining, metadata only: closed issues that name a scheduling-type bug and were closed by a commit.

    python research/mine_bench.py > data/research/bench_candidates.json

Uses the GitHub REST API through the `gh` CLI (read-only; no code is downloaded). For each hit it records the issue URL,
title, the commit that closed it (from the issue's `closed` event), that commit's first parent (the buggy side), the licence
SPDX id the API reports, and the repository's language. Everything it prints is a lead, not a benchmark entry: a human
(or the build agent) still has to check scheduling-observability, a QNX build through shims, and ground truth.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

REPOS = [
    "zeromq/libzmq", "nanomsg/nng", "eclipse/mosquitto", "libuv/libuv", "eclipse-cyclonedds/cyclonedds",
    "eProsima/Fast-DDS", "lwip-tcpip/lwip", "memcached/memcached", "redis/hiredis", "nodejs/llhttp",
    "microsoft/mimalloc", "jemalloc/jemalloc", "curl/curl", "libevent/libevent", "apache/apr",
    "ros2/rcl", "micro-ROS/rclc", "PX4/PX4-Autopilot", "NuttX/nuttx", "zephyrproject-rtos/zephyr",
    "FreeRTOS/FreeRTOS-Kernel", "mborgerding/kissfft", "dtolnay/cxx", "google/leveldb", "facebook/rocksdb",
]
TERMS = ["deadlock", "hang", "priority inversion", "lost wakeup", "missed signal", "cond_wait", "sem_wait", "starvation"]


def gh(path: str, *args: str):
    if path.startswith("search"):
        time.sleep(2.5)  # the search API allows 30 requests a minute
    p = subprocess.run(["gh", "api", path, *args], capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        print(f"gh api {path} failed: {p.stderr.strip()[:120]}", file=sys.stderr)
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None


def closed_by(repo: str, num: int) -> str | None:
    ev = gh(f"repos/{repo}/issues/{num}/events?per_page=100")
    for e in ev or []:
        if e.get("event") == "closed" and e.get("commit_id"):
            return e["commit_id"]
    return None


def main() -> int:
    seen, out = set(), []
    for repo in REPOS:
        lic = (gh(f"repos/{repo}") or {})
        spdx = ((lic.get("license") or {}).get("spdx_id")) or "unknown"
        lang = lic.get("language")
        if lang not in ("C", "C++"):
            continue
        for term in TERMS:
            q = f'repo:{repo} is:issue is:closed "{term}"'
            r = gh("search/issues", "-X", "GET", "-f", f"q={q}", "-f", "per_page=10")
            for it in (r or {}).get("items", []):
                key = (repo, it["number"])
                if key in seen:
                    continue
                seen.add(key)
                sha = closed_by(repo, it["number"])
                if not sha:
                    continue
                c = gh(f"repos/{repo}/commits/{sha}") or {}
                parents = [p["sha"] for p in c.get("parents", [])]
                out.append({"repo": repo, "issue": it["html_url"], "title": it["title"], "term": term,
                            "closed_by": sha, "parent": parents[0] if len(parents) == 1 else None,
                            "licence": spdx, "language": lang,
                            "files": [f["filename"] for f in c.get("files", [])][:6],
                            "changed_lines": (c.get("stats") or {}).get("total")})
    json.dump(out, sys.stdout, indent=1)
    print(f"{len(out)} leads", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
