"""Mine small, message-identified C/C++ concurrency fixes from public Git history."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "bugfix"
REPOS = """
nanomsg/nng zeromq/libzmq memcached/memcached redis/redis curl/curl libuv/libuv
libevent/libevent haproxy/haproxy eclipse-mosquitto/mosquitto civetweb/civetweb
eclipse-paho/paho.mqtt.c eclipse-iceoryx/iceoryx eclipse-cyclonedds/cyclonedds
eProsima/Fast-DDS FreeRTOS/FreeRTOS-Kernel apache/nuttx RIOT-OS/RIOT jemalloc/jemalloc
nginx/nginx openssl/openssl sqlite/sqlite ros2/rclcpp OpenAMP/open-amp
nanomsg/nanomsg redis/hiredis libssh2/libssh2 qnx-ports/build-files
zephyrproject-rtos/zephyr grpc/grpc opencv/opencv
""".split()
SOURCE_EXTS = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp")
SOURCE_SPECS = [f":(glob,icase)**/*{ext}" for ext in SOURCE_EXTS]
FIX = (
    r"\b(fix(es|ed|ing)?|bug ?fix(es)?|prevent(s|ed|ing)?|avoid(s|ed|ing)?|correct(s|ed|ing)?|"
    r"resolve[sd]?|eliminat(e|es|ed|ing)|work[ -]?around)\b"
)
DIRECT = {
    "deadlock": r"\bdead[ -]?locks?\b",
    "lock-order inversion": r"\b(lock[ -]?order(ing)?[ -]+(inversion|violation|deadlock)s?|inverted[ -]+lock[ -]+order)\b",
    "lost/missed wake-up": r"\b(lost|losing|miss(ed|ing|es)?|skip(ped|ping)?)\b.{0,32}\bwake[ -]?ups?\b",
    "missed signal": r"\b(miss(ed|ing|es)?|lost|losing)\b.{0,24}\bsignals?\b",
    "spurious wake-up": r"\bspurious[ -]+wake[ -]?ups?\b",
    "race": r"\b(data[ -]+race|race[ -]+(condition|window))s?\b|\braces?\b",
    "priority inversion": r"\bpriority[ -]+inversion(s)?\b",
    "livelock": r"\blive[ -]?locks?\b",
}
GUARDED = {
    "hang": r"\b(hang(s|ing)?|hung|stuck|block(s|ed|ing)?[ -]+forever|wait(s|ing)?[ -]+(forever|indefinitely))\b",
    "condition variable": r"\b(cond(ition)?[ _-]+var(iable)?s?|condvar(s)?)\b",
    "pthread_cond": r"\bpthread_cond(_[[:alnum:]_]+)?\b",
    "mutex": r"\bmutex(es)?\b|\b(pthread_mutex_[[:alnum:]_]+|k_mutex_[[:alnum:]_]+|[[:alnum:]_]+_mutex_lock)\b",
}
WAIT_CONTEXT = (
    r"\b(?:lock(?:s|ed|ing)?|mutex(?:es)?|semaphores?|futex(?:es)?|condvars?|"
    r"condition[ -]+variables?|wait[ -]+queues?|join(?:s|ed|ing)?|"
    r"\w*(?:mutex|cond|sem|futex)\w*_(?:wait|take|lock)\w*|\w+_join)\b"
)
ISSUE = re.compile(r"(?<![\w/#-])#(\d+)\b")
BOT = re.compile(r"\[bot\]|(?:^|[\W_])bot(?:$|[\W_])|dependabot|renovate|k8s-ci-robot",
                 re.IGNORECASE)
REPRODUCER = re.compile(
    r"(?im)^\s*(?:```|~~~)|^(?: {4}|\t)\S.*\n(?: {4}|\t)\S|"
    r"^\s*(?:#\d+\s+(?:0x[0-9a-f]+|\w+\s*\()|"
    r"#\d+\s+\w+\s+at\s+|(?:stack\s+trace|backtrace)\s*:|"
    r"==\d+==\s*(?:ERROR|WARNING): .*Sanitizer)"
)
PATH_EXCLUDE = re.compile(
    r"(?:^|/)(?:\.github|ci|doc|docs|documentation|examples?|samples?|benchmarks?|"
    r"tests?|testing|\w+tests|gtest|unittest|selftest|testcases?|testsuites?|testprogs?|"
    r"fuzz(?:ers|ing)?|qa)(?:/|$)|"
    r"(?:^|/)(?:test[-_][^/]+|[^/]+[-_](?:test|tests|unittest|spec)|"
    r"tests?\d*)\.(?:c|cc|cpp|cxx|h|hpp)$",
    re.IGNORECASE,
)
SHA = re.compile(rb"[a-f0-9]{40,64}")
SHOW_MARKER = re.compile(rb"\x00([a-f0-9]{40,64})\x00")
CAP_BYTES = 5_000_000_000
DISK_STOP = 4_250_000_000
BATCH = 64


class StopRun(Exception):
    """The current run has exhausted an operational limit."""


class CommandError(Exception):
    """A subprocess failed and this repository can be retried."""


def utc_now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def decode(data):
    return data.decode("utf-8", errors="replace")


def local_rx(pattern):
    return re.compile(pattern.replace("[:alnum:]", "a-z0-9"), re.IGNORECASE)


DIRECT_RX = {label: local_rx(rx) for label, rx in DIRECT.items()}
GUARDED_RX = {label: local_rx(rx) for label, rx in GUARDED.items()}
FIX_RX = local_rx(FIX)
WAIT_RX = local_rx(WAIT_CONTEXT)
ACTION = re.compile(
    r"\b(add|acquire|address|allow|apply|change|close|defer|drop|ensure|guard|"
    r"handle|hold|lock|make|move|recheck|release|remove|replace|restore|retry|"
    r"serialize|signal|stop|synchronize|unlock|update|use|wait|wake)\b", re.IGNORECASE,
)
NONFIX = re.compile(
    r"^(?:(?:\[[^\]]+\]|[\w ./+-]+:)\s*)*"
    r"(?:refactor\b|clean[ -]?up\b|add support\b|document\b|add (?:a |more )?tests?\b|"
    r"test (?:for|that)\b|revert\b|back out\b)", re.IGNORECASE,
)
COSMETIC = re.compile(
    r"\b(?:fix(?:es|ed|ing)? (?:\w+ )?(?:typo(?:s)?|spelling|formatting|style|indentation)|"
    r"style fixes|thread[ -]safety analysis warning|unused (?:variable|parameter|function|label)|"
    r"fix(?:es|ed|ing)? (?:(?:the )?documentation|warnings? in))\b", re.IGNORECASE,
)
DOC_ONLY = re.compile(r"\b(?:documentation|comment)[ -]only (?:change|update|fix)\b", re.I)
CAUSE = re.compile(
    r"\b(cause[sd]?|could|may|might|would|can|lead[s]? to|because|otherwise|"
    r"to (?:prevent|avoid|fix)|result[s]? in|introduc(?:es|ed))\b", re.IGNORECASE,
)


def message_labels(message):
    """Require repair intent as well as a concurrency keyword."""
    subject = message.splitlines()[0] if message.strip() else ""
    core = re.split(r"(?im)^\s*(?:Signed-off-by|Co-authored-by|Reviewed-by):", message)[0]
    fixes = FIX_RX.search(core)
    labels = [label for label, rx in DIRECT_RX.items() if rx.search(core)]
    if "race" in labels and re.search(r"\brace to (?:idle|sleep|halt)\b", core, re.I):
        if not re.search(r"\b(?:race condition|data race|race window)\b", core, re.I):
            labels.remove("race")
    if fixes:
        for label, rx in GUARDED_RX.items():
            if rx.search(core) and (label != "hang" or WAIT_RX.search(core)):
                labels.append(label)
    if not labels or COSMETIC.search(subject) or DOC_ONLY.search(core):
        return []
    if NONFIX.search(subject):
        # A revert qualifies when its description explains the bug it removes.
        revert = re.search(r"\b(?:revert|back out)\b", subject, re.I)
        body = core.partition("\n")[2]
        if not (revert and CAUSE.search(body) and any(rx.search(body) for rx in DIRECT_RX.values())):
            return []
    elif not fixes and not (
        ACTION.search(subject) and (CAUSE.search(core) or any(
            label != "race" and DIRECT_RX[label].search(subject) for label in labels
        ))
    ):
        return []
    return labels


def checked_clone(output, repo):
    clone = output / (".clone-" + repo.replace("/", "--"))
    if clone.resolve() != clone or clone.parent != output:
        raise ValueError(f"Unexpected clone path for {repo}")
    return clone


def production_source(repo, path):
    name = path.lower()
    if repo.lower() == "grpc/grpc" and not name.startswith(("src/core/", "include/grpc/")):
        return False
    return name.endswith(SOURCE_EXTS) and not PATH_EXCLUDE.search(name)


def delete_clone(clone):
    def make_writable(operation, path, exc_info):
        if os.name != "nt" or not isinstance(exc_info[1], PermissionError):
            raise exc_info[1]
        os.chmod(path, stat.S_IWRITE)
        operation(path)

    shutil.rmtree(clone, onerror=make_writable)


def disk_bytes(path):
    size = 0
    for folder, _, filenames in os.walk(path):
        for name in filenames:
            with contextlib.suppress(FileNotFoundError):
                size += (Path(folder) / name).stat().st_size
    return size


@contextlib.contextmanager
def writer_lock(path):
    with path.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def write_state(path, state):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read_records(path):
    records = {}
    with path.open("a+b") as stream:
        stream.seek(0)
        while line := stream.readline():
            if not line.endswith(b"\n"):
                stream.truncate(stream.tell() - len(line))
                break
            record = json.loads(line)
            key = (record["repo"], record["sha"])
            if key in records:
                raise ValueError(f"Duplicate input record {key}")
            records[key] = record
    return records


def jsonline(record):
    return json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"


class Run:
    def __init__(self, output, seconds):
        self.output = output
        self.deadline = time.monotonic() + seconds
        self.mine_deadline = self.deadline
        self.state_path = output / "state.json"
        self.data_path = output / "commits.jsonl"
        self.state = (
            json.loads(self.state_path.read_text(encoding="utf-8"))
            if self.state_path.exists() else {"version": 1, "repos": {}, "lookup": {}}
        )
        if self.state["version"] != 1:
            raise ValueError("Unsupported state file version")
        self.state["repos"] = dict(self.state["repos"])
        self.records = read_records(self.data_path)
        self.lock = Lock()
        self.stopped = Event()
        self.peak = max(self.state.get("peak_bytes", 0), disk_bytes(output))
        self.disk_checked = 0.0

    def check(self, deadline):
        if self.stopped.is_set():
            raise StopRun("disk guard or interrupt")
        now = time.monotonic()
        if now >= deadline:
            raise StopRun("time budget")
        with self.lock:
            if now - self.disk_checked >= 0.8:
                size = disk_bytes(self.output)
                self.peak = max(self.peak, size)
                self.disk_checked = now
                if size >= DISK_STOP:
                    self.stopped.set()
                    raise StopRun(f"disk guard at {size:,} bytes (cap {CAP_BYTES:,})")

    def command(self, args, *, deadline, input_data=None, capture=True):
        self.check(deadline)
        output = subprocess.PIPE if capture else subprocess.DEVNULL
        process = subprocess.Popen(
            args, cwd=self.output,
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=output, stderr=output,
            start_new_session=os.name != "nt",
        )
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(input_data, timeout=1)
                    self.check(deadline)
                    return process.returncode, stdout, stderr
                except subprocess.TimeoutExpired:
                    input_data = None
                    self.check(deadline)
        except BaseException:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   check=False)
                else:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                process.kill()
            process.communicate()
            raise

    def git(self, clone, *args, input_data=None, local=False, check=True):
        result = self.command(
            ["git", *(["--no-lazy-fetch"] if local else []),
             "-c", "credential.helper=", "-c", "http.extraHeader=",
             "-c", "gc.auto=0", "-c", "maintenance.auto=false",
             "-c", "fetch.negotiationAlgorithm=noop",
             "-C", str(clone), *args],
            deadline=self.mine_deadline, input_data=input_data,
        )
        if check and result[0]:
            # Avoid persisting transport diagnostics that could include sensitive local config.
            raise CommandError(f"git {args[0]} exited {result[0]}")
        return result if not check else result[1]

    def save(self):
        self.state["peak_bytes"] = self.peak
        write_state(self.state_path, self.state)

    def checkpoint(self, repo, progress, batch=()):
        with self.lock:
            with self.data_path.open("a", encoding="utf-8", newline="\n") as out:
                for record in batch:
                    key = (repo, record["sha"])
                    if key not in self.records:
                        out.write(jsonline(record))
                        self.records[key] = record
                if batch:
                    out.flush()
                    os.fsync(out.fileno())
            self.state["repos"][repo] = progress.copy()
            self.save()

    def mine(self, repo):
        progress = self.state["repos"].get(repo, {}).copy()
        if progress.get("status") == "complete":
            return
        clone = checked_clone(self.output, repo)
        progress["status"] = "running"
        progress.pop("error", None)
        seen = Counter(progress.get("counts", {}))
        try:
            self.check(self.mine_deadline)
            if not (clone / ".git" / "config").exists():
                if clone.exists():
                    delete_clone(clone)
                self.git(self.output, "clone", "--filter=blob:none", "--no-checkout", "--single-branch",
                         "--no-tags", f"https://github.com/{repo}.git", str(clone))
            head = progress.get("head") or decode(self.git(clone, "rev-parse", "HEAD")).strip()
            if self.git(clone, "cat-file", "-e", f"{head}^{{commit}}", local=True, check=False)[0]:
                self.git(clone, "fetch", "--no-tags", "--filter=blob:none", "origin", head)
            progress["head"] = head
            candidates = candidate_log(self, clone, head)
            progress["candidates"] = len(candidates)
            self.checkpoint(repo, progress)
            offset = progress.get("processed", 0)
            for start in range(offset, len(candidates), BATCH):
                chunk = candidates[start:start + BATCH]
                batch_counts = seen.copy()
                rows = mine_batch(self, clone, repo, chunk, batch_counts)
                seen = batch_counts
                progress.update(processed=start + len(chunk), counts=dict(seen))
                self.checkpoint(repo, progress, rows)
            progress["status"] = "complete"
        except StopRun as error:
            progress.update(status="paused", error=str(error))
        except CommandError as error:
            progress.update(status="failed", error=str(error))
        finally:
            if clone.exists():
                try:
                    delete_clone(clone)
                except OSError:
                    progress.update(status="failed", error="could not delete clone")
            self.checkpoint(repo, progress)
            print(f"{repo}: {progress['status']}, {seen['kept']} kept"
                  f" / {progress.get('candidates', 0)} candidates"
                  f"{' (' + progress['error'] + ')' if 'error' in progress else ''}", flush=True)


def candidate_log(run, clone, head):
    format_ = "--format=%H%x00%P%x00%aI%x00%an%x00%ae%x00%B"
    flags = ("log", head, "--date-order", "--no-merges", "-z", format_,
             "--extended-regexp", "--regexp-ignore-case")
    direct = run.git(clone, *flags, "--grep=" + "|".join(f"({p})" for p in DIRECT.values()))
    guarded = run.git(clone, *flags, "--all-match", "--grep=" + FIX,
                      "--grep=" + "|".join(f"({p})" for p in GUARDED.values()))
    by_sha = {}
    for data in (direct, guarded):
        fields = data.split(b"\0")[:-1]
        if len(fields) % 6:
            raise CommandError("unexpected git log record framing")
        for index in range(0, len(fields), 6):
            sha, parents, date, name, email, message = map(decode, fields[index:index + 6])
            if not SHA.fullmatch(sha.encode()) or " " in parents:
                raise CommandError("unexpected git log commit ID or parent count")
            by_sha[sha] = (sha, parents or None, date, bool(BOT.search(name + " " + email)), message)
    # Hash is the tie-breaker, independent of the ordering of the two Git walks.
    return sorted(by_sha.values(), key=lambda row: (row[2], row[0]), reverse=True)


def raw_changes(run, clone, shas):
    if not shas:
        return {}
    input_data = ("\n".join(shas) + "\n").encode()
    raw = run.git(clone, "diff-tree", "--stdin", "-r", "--root", "--raw", "-z", "--no-renames",
                  "--no-abbrev", input_data=input_data)
    changes = defaultdict(list)
    tokens = iter(raw.split(b"\0")[:-1])
    sha = None
    for token in tokens:
        if SHA.fullmatch(token):
            sha = decode(token)
        elif token.startswith(b":") and sha is not None:
            old_mode, new_mode, old, new, _ = token[1:].split()
            blobs = [decode(oid) for mode, oid in ((old_mode, old), (new_mode, new))
                     if mode.startswith(b"100") or mode == b"120000"]
            changes[sha].append((decode(next(tokens)), blobs))
        else:
            raise CommandError("unexpected git diff-tree record framing")
    return changes


def prefetch(run, clone, blobs):
    if not blobs:
        return
    input_data = ("\n".join(sorted(blobs)) + "\n").encode()
    checked = run.git(clone, "cat-file", "--batch-check=%(objectname) %(objecttype)",
                      input_data=input_data, local=True)
    missing = [line.split()[0] for line in checked.splitlines() if line.endswith(b" missing")]
    if missing:
        # Batch the lazy object requests before show instead of one fetch per comparison.
        # If the batch is rejected, show still gets Git's normal lazy-fetch retry.
        run.git(clone, "fetch", "origin", "--no-tags", "--no-write-fetch-head", "--no-auto-gc",
                "--recurse-submodules=no", "--filter=blob:none", "--stdin",
                input_data=b"\n".join(missing) + b"\n", check=False)


def show_sections(run, clone, shas, options, paths=()):
    if not shas:
        return {}
    data = run.git(clone, "show", "--format=%x00%H%x00", "--no-renames", "--no-ext-diff",
                   "--no-textconv", "--no-color", *options, *shas, "--", *paths)
    sections = SHOW_MARKER.split(data)
    by_sha = {decode(sha): content for sha, content in zip(sections[1::2], sections[2::2], strict=True)}
    if by_sha.keys() != set(shas):
        raise CommandError("git show did not return every requested commit")
    return by_sha


def mine_batch(run, clone, repo, candidates, counts):
    labeled = {}
    for sha, parent, date, bot, message in candidates:
        labels = message_labels(message)
        if labels:
            labeled[sha] = (parent, date, bot, message, labels)
        else:
            counts["message"] += 1
    changes = raw_changes(run, clone, labeled)
    eligible = {}
    blobs = set()
    for sha in labeled:
        files = changes.get(sha, [])
        if len(files) > 4:
            counts["file_limit"] += 1
        elif not any(production_source(repo, path) for path, _ in files):
            counts["no_production_source"] += 1
        else:
            eligible[sha] = [path for path, _ in files]
            blobs.update(oid for _, object_ids in files for oid in object_ids)
    prefetch(run, clone, blobs)
    totals = {}
    for sha, section in show_sections(run, clone, list(eligible), ("-z", "--numstat")).items():
        added = deleted = 0
        for numstat in section.lstrip(b"\0\n").split(b"\0"):
            if not numstat:
                continue
            plus, minus, _ = numstat.split(b"\t", 2)
            if plus == b"-" or minus == b"-":
                counts["binary"] += 1
                break
            added += int(plus)
            deleted += int(minus)
        else:
            if added + deleted > 250:
                counts["line_limit"] += 1
            else:
                totals[sha] = (added, deleted)

    rows = []
    for sha, section in show_sections(
        run, clone, list(totals), ("--patch", "-U3"), SOURCE_SPECS,
    ).items():
        if not section.lstrip(b"\n").startswith(b"diff --git "):
            counts["empty_source_diff"] += 1
            continue
        parent, date, bot, message, labels = labeled[sha]
        added, deleted = totals[sha]
        refs = list(dict.fromkeys(int(n) for n in ISSUE.findall(message) if len(n) <= 10))
        rows.append({
            "repo": repo, "sha": sha, "parent_sha": parent, "date": date, "author_is_bot": bot,
            "message": message, "files": eligible[sha], "diff": decode(section.lstrip(b"\n")),
            "added_lines": added, "deleted_lines": deleted, "keywords_matched": labels, "issue_refs": refs,
            "issue_text": None, "license_spdx": None, "has_reproducer_hint": bool(REPRODUCER.search(message)),
        })
        counts["kept"] += 1
    return rows


def lookup_query(repo, refs):
    owner, name = map(json.dumps, repo.split("/"))
    issues = " ".join(f"i{n}: issue(number: {n}) {{ title body }}" for n in refs)
    query = (
        f"{{ repository(owner: {owner}, name: {name}) {{ isPrivate licenseInfo {{ spdxId }} "
        f"{issues} }} rateLimit {{ remaining resetAt }} }}"
    )
    return json.dumps({"query": query}).encode()


def wait_for_limit(run, delay):
    until = time.monotonic() + max(1, delay)
    print(f"GitHub rate limit. Waiting {max(1, int(delay))} seconds within the run budget.", flush=True)
    while time.monotonic() < until:
        run.check(run.deadline)
        time.sleep(max(0, min(1, until - time.monotonic())))


def lookup(run, repo, refs):
    for fallback_delay in (30, 60, 120):
        _, stdout, stderr = run.command(
            ["gh", "api", "graphql", "--input", "-"], deadline=run.deadline,
            input_data=lookup_query(repo, refs),
        )
        try:
            response = json.loads(stdout)
        except json.JSONDecodeError:
            response = {}
        data = response.get("data") or {}
        errors = response.get("errors") or []
        limit = data.get("rateLimit") or {}
        diagnostic = decode(stderr).lower()
        limited = (
            limit.get("remaining") == 0
            or "rate limit" in diagnostic
            or any(e.get("type") in {"RATE_LIMITED", "RATE_LIMIT"} for e in errors)
        )
        if limited:
            reset = limit.get("resetAt")
            delay = (
                (datetime.fromisoformat(reset.replace("Z", "+00:00")) -
                 datetime.now(UTC)).total_seconds() + 2
                if reset else fallback_delay
            )
            wait_for_limit(run, delay)
            continue
        public = data.get("repository")
        if public and public.get("isPrivate") is False:
            return public
        return None
    return None


def enrich(run):
    state = run.state["lookup"]
    try:
        auth, _, _ = run.command(["gh", "auth", "status", "--hostname", "github.com"],
                                 deadline=run.deadline, capture=False)
    except FileNotFoundError:
        auth = 1
    if auth:
        run.state["lookup_status"] = "gh login unavailable"
        print("GitHub metadata skipped because gh login is unavailable.", flush=True)
        return
    # Keep only lookup outcomes in the state. The issue text lives in the JSONL.
    grouped = defaultdict(list)
    for record in run.records.values():
        grouped[record["repo"]].append(record)
    try:
        for repo, records in grouped.items():
            repo_state = state.setdefault(repo, {"issues": {}})
            issues = repo_state["issues"]
            refs = sorted({r["issue_refs"][0] for r in records if r["issue_refs"]}
                          - {int(n) for n in issues})
            for start in range(0, max(len(refs), int("license" not in repo_state)), 32):
                batch = refs[start:start + 32]
                result = lookup(run, repo, batch)
                if result is None:
                    repo_state["errors"] = repo_state.get("errors", 0) + 1
                    continue
                license_ = (result.get("licenseInfo") or {}).get("spdxId")
                repo_state["license"] = license_ not in (None, "NOASSERTION", "NONE")
                # A prior run may have died before rewriting the JSONL. Keep its
                # previous data unless this response covers the same issue.
                for record in records:
                    record["license_spdx"] = license_ if repo_state["license"] else None
                    ref = record["issue_refs"][0] if record["issue_refs"] else None
                    if ref in batch and f"i{ref}" in result:
                        issue = result[f"i{ref}"]
                        value = issue["title"] + "\n" + (issue["body"] or "")[:3000] if issue else None
                        record["issue_text"] = value
                        record["has_reproducer_hint"] = bool(
                            REPRODUCER.search(record["message"]) or REPRODUCER.search(value or "")
                        )
                for ref in batch:
                    if f"i{ref}" in result:
                        issues[str(ref)] = result[f"i{ref}"] is not None
            # Use an already enriched record when a resumed mining run adds rows.
            licenses = [r["license_spdx"] for r in records if r["license_spdx"]]
            texts = {r["issue_refs"][0]: r["issue_text"]
                     for r in records if r["issue_refs"] and r["issue_text"]}
            for record in records:
                if licenses:
                    record["license_spdx"] = licenses[0]
                if record["issue_refs"] and record["issue_refs"][0] in texts:
                    record["issue_text"] = texts[record["issue_refs"][0]]
                    record["has_reproducer_hint"] |= bool(REPRODUCER.search(record["issue_text"]))
        pending = sum(
            "license" not in state.get(repo, {}) or any(
                r["issue_refs"] and str(r["issue_refs"][0])
                not in state.get(repo, {}).get("issues", {}) for r in records
            )
            for repo, records in grouped.items()
        )
        run.state["lookup_status"] = f"{pending} repositories with pending metadata"
    except StopRun as error:
        run.state["lookup_status"] = f"paused: {error}"
    finally:
        temp = run.data_path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            for record in run.records.values():
                stream.write(jsonline(record))
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(run.data_path)
        run.save()
    print(f"Metadata: {run.state['lookup_status']}.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos", nargs="+", help="public GitHub owner/name pairs")
    parser.add_argument("--seconds", type=int, default=1500, help="wall-time budget for this run")
    parser.add_argument("--workers", type=int, default=3, choices=range(1, 5))
    phases = parser.add_mutually_exclusive_group()
    phases.add_argument("--mine-only", action="store_true")
    phases.add_argument("--enrich-only", action="store_true")
    args = parser.parse_args()
    if args.seconds < 1 or args.seconds > 1800:
        parser.error("--seconds must be between 1 and 1800")
    repo_pattern = r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+"
    if any(not re.fullmatch(repo_pattern, repo) or repo.split("/")[1] in {".", ".."}
           for repo in args.repos or []):
        parser.error("--repos requires public GitHub owner/name pairs")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT.resolve()
    # Keep temporary Git files in the mining directory and use gh's existing login.
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GIT_ASKPASS", "SSH_ASKPASS"):
        with contextlib.suppress(KeyError):
            del os.environ[name]
    os.environ.update({name: str(output) for name in ("TMPDIR", "TMP", "TEMP")})
    os.environ.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GH_PROMPT_DISABLED="1",
                      GH_NO_UPDATE_NOTIFIER="1", GH_NO_EXTENSION_UPDATE_NOTIFIER="1", NO_COLOR="1")
    with writer_lock(output / ".writer.lock"):
        run = Run(output, args.seconds)
        run.state["started_at"] = utc_now()
        try:
            if not args.enrich_only:
                if not args.mine_only:
                    run.mine_deadline -= min(120, args.seconds / 4)
                known = run.state["repos"]
                canonical = {name.lower(): name for name in known}
                requested = args.repos or [*REPOS, *known]
                selected = list(dict.fromkeys(canonical.setdefault(name.lower(), name) for name in requested))
                for repo in selected:
                    known.setdefault(repo, {"status": "pending"})
                run.save()
                with ThreadPoolExecutor(max_workers=args.workers) as workers:
                    futures = [workers.submit(run.mine, repo) for repo in selected]
                    try:
                        for future in futures:
                            future.result()
                    except KeyboardInterrupt:
                        run.stopped.set()
                        raise
            if not args.mine_only and run.records:
                enrich(run)
        except StopRun as error:
            print(f"Stopped: {error}", flush=True)
        finally:
            run.state["finished_at"] = utc_now()
            run.save()
        print(f"{len(run.records):,} unique commits. Observed peak {run.peak:,} bytes.", flush=True)


if __name__ == "__main__":
    main()
