"""Label mined diffs with auditable, multi-label concurrency fix heuristics."""

from __future__ import annotations

import argparse
import html
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "bugfix" / "commits.jsonl"
SEED = 20261125
SHAPES = (
    "add-predicate-loop", "check-flag-before-wait", "lock-order", "move-work-out-of-lock",
    "add-lock", "remove-lock", "use-trylock-or-timeout", "sem-to-mutex",
    "priority-inheritance", "signal-under-lock", "signal-outside-lock", "signal-to-broadcast",
    "atomic-or-volatile", "add-cancel-or-shutdown-path", "async-signal-safety",
    "complete-unlock-on-exit", "mask-interrupts-around-state", "change-lock-target",
    "retain-object-until-work-finishes", "serialize-work-on-owner-queue", "other",
)

LOCK = re.compile(
    r"\b((?:[a-z]\w*_)?(?:(?:nxr?|r)?mutex_lock|mtx_lock|mu_lock|evlock\d*_lock|"
    r"sched_lock|spin_?lock|rwlock_(?:rdlock|wrlock|lock)|rlock|wlock|rdlock|wrlock)|"
    r"Acquire(?:SRWLock(?:Exclusive|Shared)|Mutex)|EnterCriticalSection|"
    r"(?:[a-z]\w*_)?(?:read_lock|write_lock|lock_acquire|lock_mutex)|EVDNS_LOCK|"
    r"[\w.>\-]+(?:\.|->)(?:lock|lock_shared))\s*\(([^;\n]*)", re.I,
)
UNLOCK = re.compile(
    r"\b((?:[a-z]\w*_)?(?:(?:nxr?|r)?mutex_unlock|mtx_unlock|mu_unlock|evlock\d*_unlock|"
    r"sched_unlock|thread_unlock|spin_?unlock|"
    r"rwlock_(?:rdunlock|wrunlock|unlock)|runlock|wunlock|rdunlock|wrunlock)|"
    r"Release(?:SRWLock(?:Exclusive|Shared)|Mutex)|LeaveCriticalSection|"
    r"(?:[a-z]\w*_)?(?:read_unlock|write_unlock|lock_release|unlock_mutex)|EVDNS_UNLOCK|"
    r"[\w.>\-]+(?:\.|->)(?:unlock|unlock_shared))\s*\(([^;\n]*)", re.I,
)
RAII = re.compile(
    r"\b((?:std::)?(?:lock_guard|unique_lock|scoped_lock|shared_lock)(?:<[^>]*>)?|"
    r"(?:Reader|Writer|Instrumented)?MutexLock|AutoLock|USBHost::Lock)\s+\w+\s*[({]\s*([^;,\n)}]+)"
)
WAIT = re.compile(
    r"\b((?:\w+_)?(?:cond(?:var)?|cv)_(?:timed)?wait\w*|"
    r"(?:\w+_)?(?:sem|semaphore|completion)_(?:timed)?(?:wait|take)\w*|"
    r"[\w.>\-]+(?:\.|->)wait(?:_until|_for)?|SleepConditionVariable\w*|"
    r"futex(?:_noasync|_async)?(?=\s*\([^;\n]*\bFUTEX_WAIT\w*\b))\s*\(([^;\n]*)", re.I,
)
WAKE_ONE = re.compile(
    r"\b((?:\w+_)?(?:cond(?:var)?|cv)_(?:signal|wake_?one|wake1)|"
    r"[\w.>\-]+(?:\.|->)notify_?one|WakeConditionVariable)\s*\(([^;\n]*)", re.I,
)
WAKE_ALL = re.compile(
    r"\b((?:\w+_)?(?:cond(?:var)?|cv)_(?:broadcast|wake_?all)|nni_cv_wake|"
    r"[\w.>\-]+(?:\.|->)notify_?all|WakeAllConditionVariable)\s*\(([^;\n]*)", re.I,
)
TRY = re.compile(
    r"\b(?:\w*try_?lock\w*|\w*(?:timed_?(?:lock|wait)|wait_?(?:for|until|timeout))\w*)\s*\(", re.I,
)
ERROR_HANDLING = re.compile(r"\b(?:if|switch)\s*\(|\b(?:ETIMEDOUT|EBUSY|EAGAIN|timeout|break|goto)\b", re.I)
INDEFINITE = re.compile(r"\b(?:K_FOREVER|portMAX_DELAY|INFINITE|osWaitForever|WAIT_FOREVER)\b")
BOUNDED = re.compile(r"\b(?:K_NO_WAIT|K_MSEC|K_USEC|K_TICKS|K_SECONDS|pdMS_TO_TICKS)\b")
SEMAPHORE = re.compile(r"\b(?:\w+_)?(?:sem(?:aphore)?_(?:wait|post|take|give|init)|sem_t)\b", re.I)
MUTEX = re.compile(r"\b(?:\w+_)?(?:(?:nxr?)?mutex|mtx)(?:_\w+)?\b", re.I)
PRIO = re.compile(r"\b(?:PTHREAD(?:_MUTEX_DEFAULT)?|MUTEX|LOCK|SEM)_PRIO_INHERIT\b")
ATOMIC = re.compile(
    r"\b(?:volatile|_Atomic|std::atomic\w*|(?:\w+_)?atomic_(?:load|store|exch\w*|compare\w*|"
    r"fetch\w*|flag\w*|init|int|bool|t|ptr|u?int\d*_t|cas|inc|dec|add|sub|bts|btr)|"
    r"__atomic_\w+|__sync_\w+|Interlocked\w+|gpr_atm_\w+)\b", re.I,
)
SHUTDOWN = re.compile(r"\b\w*(?:cancel|shutdown|terminat|interrupt_wait|stop_thread|close_wait)\w*\s*\(", re.I)
EXIT_CONTEXT = re.compile(r"shutdown|stopping|closed?|cancel|terminat|destroy|(?:worker|thread)_(?:exit|stop)", re.I)
EXIT = re.compile(r"\b(?:return|goto|break|continue)\b")
MASK = re.compile(
    r"\b(?:\w+_)?(?:irq_(?:disable|lock)|irqsave|enter_critical_section)\s*\(|"
    r"\b(?:(?:port|task)ENTER_CRITICAL(?:_FROM_ISR)?|__disable_irq)\s*\("
)
UNMASK = re.compile(
    r"\b(?:\w+_)?(?:irq_(?:restore|unlock|enable)|irqrestore|leave_critical_section)\s*\(|"
    r"\b(?:(?:port|task)EXIT_CRITICAL(?:_FROM_ISR)?|__enable_irq)\s*\("
)
THIS_CAPTURE = re.compile(r"\[\s*this\b")
REF_CAPTURE = re.compile(r"\[\s*\w+\s*=\s*(?:[\w:]*Ref(?:As\w+)?|shared_from_this)\s*\(")
RETAIN = re.compile(r"\b([\w.>\-]+)(?:\.|->)(?:Ref|AddRef|retain|ref)\s*\(")
RELEASE = re.compile(r"\b([\w.>\-]+)(?:\.|->)(?:Unref|UnRef|ReleaseRef|unref|release)\s*\(")
DEFAULT_QUEUE = re.compile(r"\b(?:k_work_(?:submit|schedule|reschedule)|queue_work|schedule_work)\s*\(")
OWNER_QUEUE = re.compile(r"\b(?:k_work_(?:submit_to_queue|(?:re)?schedule_for_queue)|queue_work_on)\s*\(")
UNSAFE = re.compile(
    r"\b(malloc|calloc|realloc|free|\w*printf|\w*fopen|syslog|\w*log\w*|"
    r"pthread_mutex_\w+|pthread_cond_\w+|exit|strsignal)\s*\(",
)
HANDLER = re.compile(
    r"(?:\bsig_?handler|\bsignal_?handler|\b\w+SignalHandler|\bsig(?:int|term|chld|hup)_?handler|"
    r"\b(?:sigaction|signal)\s*\()",
    re.I,
)
ORDER_DOC = re.compile(
    r"(?:lock(?:ing)?|mutex).{0,45}(?:lock order|acquisition order|must (?:always )?be (?:taken|held)|"
    r"(?:acquir|lock|tak)[a-z]+ before)|\b(?:global|consistent|same|fixed)\s+(?:lock|locking)\s+order\b",
    re.I,
)
GUARD = re.compile(r"\b(if|while)\s*\((.+)\)")
COMMENT = re.compile(r"^\s*(?://|/\*|\*/|\* +[A-Za-z])")


@dataclass
class Hunk:
    heading: str
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)


def parse_hunks(diff):
    files = []
    hunk = None
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            files.append([])
            hunk = None
        elif line.startswith("@@ ") and files:
            hunk = Hunk(line.partition(" @@")[2].strip())
            files[-1].append(hunk)
        elif hunk is not None:
            if line.startswith("-"):
                hunk.old.append(line[1:])
                hunk.removed.append(line[1:])
            elif line.startswith("+"):
                hunk.new.append(line[1:])
                hunk.added.append(line[1:])
            elif line.startswith(" "):
                hunk.old.append(line[1:])
                hunk.new.append(line[1:])
    return files


def normalize(line):
    return re.sub(r"\s+", "", line)


def executable(lines):
    return [line for line in lines if line.strip() and not COMMENT.match(line)]


def events(lines, pattern):
    result = []
    for index, line in enumerate(lines):
        if COMMENT.match(line):
            continue
        for match in pattern.finditer(line):
            arg = normalize(re.split(r"[,)]", match[2], maxsplit=1)[0])
            result.append((index, (match[1], arg)))
    return result


def guarded_waits(lines):
    waits = {}
    for index, event in events(lines, WAIT):
        for start in range(index, max(-1, index - 5), -1):
            fragment = " ".join(lines[start:index + 1])
            fragment = WAIT.split(fragment, maxsplit=1)[0]
            guard = GUARD.search(fragment)
            if guard and not re.search(r";|}\s*[\w{]", fragment[guard.end():]):
                waits[event] = (guard[1], normalize(guard[2]))
                break
    return waits


def relative_order(old, new, first, second):
    """Return -1/+1 when the same two calls cross, with the sign for the new order."""
    previous = {(a, b): ai < bi
                for ai, a in events(old, first) for bi, b in events(old, second) if ai != bi and a != b}
    for ai, a in events(new, first):
        for bi, b in events(new, second):
            if ai != bi and (a, b) in previous and previous[a, b] != (ai < bi):
                return -1 if ai < bi else 1
    return 0


def work_moved(old, new):
    old_unlock = {key: i for i, key in events(old, UNLOCK)}
    new_unlock = {key: i for i, key in events(new, UNLOCK)}
    for key in old_unlock.keys() & new_unlock.keys():
        before = {normalize(line) for line in executable(old[:old_unlock[key]]) if ";" in line}
        after = {normalize(line) for line in executable(new[new_unlock[key] + 1:]) if ";" in line}
        for line in before & after:
            if not any(rx.search(line) for rx in (LOCK, UNLOCK, WAKE_ONE, WAKE_ALL, WAIT)):
                return True
    return False


def guard_scope_end(lines, index):
    nesting = 0
    for position in range(index + 1, len(lines)):
        line = lines[position]
        if not COMMENT.match(line):
            nesting += line.count("{") - line.count("}")
        if nesting < 0:
            return position
    return len(lines)


def raii_scope_shrunk(hunk):
    braces = {line.strip() for line in hunk.added}
    if not {"{", "}"}.issubset(braces):
        return False
    old = {key: pos for pos, key in events(hunk.old, RAII)}
    for pos, key in events(hunk.new, RAII):
        if key not in old:
            continue
        old_end = guard_scope_end(hunk.old, old[key])
        new_end = guard_scope_end(hunk.new, pos)
        before = {normalize(line) for line in executable(hunk.old[old[key] + 1:old_end]) if ";" in line}
        after = {normalize(line) for line in executable(hunk.new[new_end + 1:]) if ";" in line}
        if before & after:
            return True
    return False


def wake_target(name, arg):
    return re.sub(r"(?:\.|->)[A-Za-z_]\w*$", "", name) if "." in name or "->" in name else arg


def unlock_on_exit(hunk):
    old = Counter(key for _, key in events(hunk.removed, UNLOCK))
    releases = Counter(key for _, key in events(hunk.added, UNLOCK)) - old
    for index, key in events(hunk.new, UNLOCK):
        if key in releases and any(EXIT.search(line) for line in hunk.new[index:index + 4]):
            return True
    return False


def cleanup_jump(hunk):
    if not any(re.search(r"\breturn\b", line) for line in executable(hunk.removed)):
        return False
    targets = {target for line in executable(hunk.added) for target in re.findall(r"\bgoto\s+(\w+)\s*;", line)}
    for index, line in enumerate(hunk.new):
        match = re.match(r"(\w+)\s*:", line.strip())
        if match and match[1] in targets and events(hunk.new[index + 1:index + 5], UNLOCK):
            return True
    return False


def changed_lock_target(hunk):
    for pattern in (LOCK, RAII):
        old = [key for _, key in events(hunk.removed, pattern)]
        new = [key for _, key in events(hunk.added, pattern)]
        if len(old) == len(new) == 1 and old[0][0] == new[0][0] and old[0][1] != new[0][1]:
            if pattern is RAII or (
                old[0][1] in {arg for _, (_, arg) in events(hunk.old, UNLOCK)}
                and new[0][1] in {arg for _, (_, arg) in events(hunk.new, UNLOCK)}
            ):
                return True
    return False


def hunk_shapes(hunk, labels):
    added = "\n".join(executable(hunk.added))
    removed = "\n".join(executable(hunk.removed))
    new = "\n".join(hunk.new)
    before = guarded_waits(hunk.old)
    after = guarded_waits(hunk.new)
    for event in before.keys() & after.keys():
        old_kind, old_condition = before[event]
        new_kind, new_condition = after[event]
        if old_kind == "if" and new_kind == "while":
            labels.add("add-predicate-loop")
        elif old_condition != new_condition and (
            new_condition.count("&&") > old_condition.count("&&")
            or new_condition.count("||") > old_condition.count("||")
        ):
            labels.add("check-flag-before-wait")
    if set(after) - set(before) and events(hunk.old, WAIT):
        if re.search(r"\bwhile\s*\(", added):
            labels.add("add-predicate-loop")
        if re.search(r"\bif\s*\(", added) and re.search(
            r"\b\w*(?:flag|ready|running|pending|stop|done|empty|clos|quit)\w*\b", added, re.I,
        ):
            labels.add("check-flag-before-wait")

    if relative_order(hunk.old, hunk.new, LOCK, LOCK) or ORDER_DOC.search("\n".join(hunk.added)):
        labels.add("lock-order")
    if work_moved(hunk.old, hunk.new) or raii_scope_shrunk(hunk):
        labels.add("move-work-out-of-lock")
    old_wait = WAIT.search(removed)
    uses_timed_api = TRY.search(added) and (LOCK.search(removed) or old_wait)
    bounds_existing_wait = old_wait and WAIT.search(added) and INDEFINITE.search(removed) and BOUNDED.search(added)
    if (uses_timed_api or bounds_existing_wait) and ERROR_HANDLING.search(new):
        labels.add("use-trylock-or-timeout")
    if PRIO.search(added):
        labels.add("priority-inheritance")
    for wake in (WAKE_ONE, WAKE_ALL):
        over_unlock = relative_order(hunk.old, hunk.new, wake, UNLOCK)
        over_lock = relative_order(hunk.old, hunk.new, wake, LOCK)
        if over_unlock == -1 or over_lock == 1:
            labels.add("signal-under-lock")
        if over_unlock == 1 or over_lock == -1:
            labels.add("signal-outside-lock")
    one = {wake_target(name, arg) for _, (name, arg) in events(hunk.removed, WAKE_ONE)}
    all_ = {wake_target(name, arg) for _, (name, arg) in events(hunk.added, WAKE_ALL)}
    if one & all_:
        labels.add("signal-to-broadcast")
    if Counter(ATOMIC.findall(added)) - Counter(ATOMIC.findall(removed)):
        labels.add("atomic-or-volatile")
    if (SHUTDOWN.search(added) and not SHUTDOWN.search(removed)) or (
        (WAKE_ONE.search(added) or WAKE_ALL.search(added)) and not (
            WAKE_ONE.search(removed) or WAKE_ALL.search(removed)
        ) and EXIT_CONTEXT.search(hunk.heading + "\n" + new)
    ):
        labels.add("add-cancel-or-shutdown-path")
    if UNSAFE.search(removed) and HANDLER.search(hunk.heading + "\n" + "\n".join(hunk.old)):
        if Counter(UNSAFE.findall(removed)) - Counter(UNSAFE.findall(added)):
            labels.add("async-signal-safety")
    if changed_lock_target(hunk):
        labels.add("change-lock-target")
    if THIS_CAPTURE.search(removed) and REF_CAPTURE.search(added):
        labels.add("retain-object-until-work-finishes")
    if cleanup_jump(hunk):
        labels.add("complete-unlock-on-exit")


def lock_changes(before, after):
    acquired = len(events(after, LOCK)) - len(events(before, LOCK))
    released = len(events(after, UNLOCK)) - len(events(before, UNLOCK))
    raii = sum(bool(RAII.search(line)) for line in after) - sum(bool(RAII.search(line)) for line in before)
    added = (acquired > 0 and released > 0) or raii > 0
    removed = (acquired < 0 and released < 0) or raii < 0
    return added, removed


def classify(files):
    labels = set()
    for file in files:
        before = executable(line for hunk in file for line in hunk.removed)
        after = executable(line for hunk in file for line in hunk.added)
        added_lock, removed_lock = lock_changes(before, after)
        removed_sems = SEMAPHORE.findall("\n".join(before))
        added_sems = SEMAPHORE.findall("\n".join(after))
        if len(removed_sems) > len(added_sems) and MUTEX.search("\n".join(after)) and added_lock:
            labels.add("sem-to-mutex")
        if added_lock:
            labels.add("add-lock")
        if removed_lock:
            labels.add("remove-lock")
        if not added_lock and any(unlock_on_exit(hunk) for hunk in file):
            old_unlocks = len(events(before, UNLOCK))
            if len(events(after, UNLOCK)) > old_unlocks:
                labels.add("complete-unlock-on-exit")
        new_text = "\n".join(after)
        old_text = "\n".join(before)
        newly_retained = Counter(RETAIN.findall(new_text)) - Counter(RETAIN.findall(old_text))
        newly_released = Counter(RELEASE.findall(new_text)) - Counter(RELEASE.findall(old_text))
        if newly_retained & newly_released:
            labels.add("retain-object-until-work-finishes")
        if DEFAULT_QUEUE.search(old_text) and OWNER_QUEUE.search(new_text):
            labels.add("serialize-work-on-owner-queue")
        if len(MASK.findall(new_text)) > len(MASK.findall(old_text)) and (
            len(UNMASK.findall(new_text)) > len(UNMASK.findall(old_text))
        ):
            labels.add("mask-interrupts-around-state")
        for hunk in file:
            hunk_shapes(hunk, labels)
    return [shape for shape in SHAPES if shape in labels] or ["other"]


def read_rows(path):
    with path.open(encoding="utf-8") as source:
        rows = [json.loads(line) for line in source]
    return sorted(rows, key=lambda row: (row["repo"], row["sha"]))


def select(rows, count, salt):
    return random.Random(f"{SEED}/{salt}").sample(rows, min(count, len(rows)))


def md(text):
    return html.escape(text, quote=False).replace("|", "\\|").replace("`", "\\`").replace("[", "\\[")


def subject(row):
    return row["message"].splitlines()[0].strip() or "(empty subject)"


def example(row):
    repo, sha = row["repo"], row["sha"]
    return f"- {md(subject(row))} [{repo} `{sha}`](https://github.com/{repo}/commit/{sha})"


def table(header, rows):
    return [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(map(str, row)) + " |" for row in rows),
    ]


def render(rows, state):
    by_shape = defaultdict(list)
    sizes = {}
    for row in rows:
        files = parse_hunks(row["diff"])
        sizes[row["repo"], row["sha"]] = sum(
            len(hunk.added) + len(hunk.removed) for file in files for hunk in file
        )
        for shape in classify(files):
            by_shape[shape].append(row)
    by_repo = Counter(row["repo"] for row in rows)
    by_year = Counter(row["date"][:4] for row in rows)
    by_repo_year = defaultdict(Counter)
    for row in rows:
        by_repo_year[row["repo"]][row["date"][:4]] += 1
    by_license = Counter(row["license_spdx"] or "No SPDX ID" for row in rows)
    hint = sum(row["has_reproducer_hint"] for row in rows)
    with_ref = sum(bool(row["issue_refs"]) for row in rows)
    with_text = sum(row["issue_text"] is not None for row in rows)
    only_other = len(by_shape["other"])
    share = only_other / len(rows) if rows else 0.0
    percent = 100 * hint / len(rows) if rows else 0.0
    repos = state.get("repos", {})
    peak = state.get("peak_bytes", 0)
    lines = [
        "# Concurrency bug-fix mining", "",
        f"Kept **{len(rows):,} commits** from **{len(by_repo)} repositories**. "
        f"**{hint:,} ({percent:.1f}%)** have a reproducer hint. "
        f"GitHub returned issue text for **{with_text:,} of {with_ref:,}** commits with an issue reference.",
        "",
    ]
    if share > 0.4:
        lines.append(f"**Uncovered share exceeds 40%. {only_other:,} commits ({share:.1%}) are `other`.**")
    else:
        lines.append(f"**{only_other:,} commits ({share:.1%})** are `other`.")
    lines += [
        "",
        "The miner searched the history reachable from each pinned default-branch tip. "
        "The repository table records progress if a scan stopped early. The file and line caps apply across "
        "the entire commit. The stored patch contains only C/C++ files and has three lines of context. "
        "Years come from each commit's author date. Licence IDs reflect current GitHub repository metadata.",
        "",
    ]
    if peak:
        lines += [f"Peak observed disk usage for the mining directory was **{peak:,} bytes**.", ""]
    counts = Counter()
    for repo in repos.values():
        counts.update(repo.get("counts", {}))
    lines += ["## Repositories", ""]
    if repos:
        candidate_total = sum(repo.get("candidates", 0) for repo in repos.values())
        processed_total = sum(repo.get("processed", 0) for repo in repos.values())
        lines += [
            f"Checked {processed_total:,} of {candidate_total:,} Git message candidates in {len(repos)} repositories.",
            "",
        ]
    lines += table(("Repository", "Kept", "Candidates checked / found", "Status"), (
        (
            name, by_repo[name],
            f"{repos[name].get('processed', 0):,} / {repos[name].get('candidates', 0):,}" if name in repos else "—",
            md(" · ".join(str(repos[name][k]) for k in ("status", "error") if k in repos[name]))
            if name in repos else "—",
        )
        for name in sorted(repos.keys() | by_repo.keys(), key=lambda name: (-by_repo[name], name.lower()))
    ))
    if counts:
        reject = {reason: count for reason, count in counts.items() if reason != "kept"}
        lines += ["", "Rejections by first applicable check.", ""]
        lines += table(("Check", "Commits"), ((key.replace("_", " "), count) for key, count in sorted(reject.items())))
    lines += ["", "## Author years", ""]
    lines += table(("Year", "Kept"), sorted(by_year.items()))
    lines += ["", "<details><summary>Year counts by repository</summary>", ""]
    lines += table(("Repository", "Author year (kept commits)"), (
        (repo, ", ".join(f"{year} ({count})" for year, count in sorted(years.items())))
        for repo, years in sorted(by_repo_year.items(), key=lambda item: item[0].lower())
    ))
    lines += ["", "</details>"]
    lines += ["", "## Licence mix", ""]
    lines += table(("SPDX ID", "Commits"), sorted(by_license.items()))
    lines += [
        "", "## Fix shapes", "",
        "A commit can receive several shape labels. `other` is exclusive. Median size counts inserted "
        "and deleted C/C++ lines in the stored patch. Each sample is drawn without replacement with "
        f"seed {SEED}. Shapes with fewer than 20 matches show every match.", "",
    ]
    lines += table(("Shape", "Commits", "Repos", "Median changed C/C++ lines"), (
        (
            f"`{shape}`", len(members), len({r["repo"] for r in members}),
            f"{median(sizes[r['repo'], r['sha']] for r in members):g}" if members else "—",
        )
        for shape, members in ((shape, by_shape[shape]) for shape in SHAPES)
    ))
    lines += ["", "## Random examples"]
    for shape in SHAPES:
        sample = select(by_shape[shape], 20, shape)
        lines += ["", f"<details><summary>{shape} ({len(sample)} examples)</summary>", ""]
        lines.extend(map(example, sample))
        if not sample:
            lines.append("No matches.")
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=INPUT)
    parser.add_argument("--output", type=Path, help="write the measured Markdown report")
    parser.add_argument("--sample-other", type=int, help="print a separate random sample for manual audit")
    args = parser.parse_args()
    rows = read_rows(args.input)
    if args.sample_other is not None:
        others = [row for row in rows if classify(parse_hunks(row["diff"])) == ["other"]]
        for row in select(others, args.sample_other, "manual-audit"):
            print(f"{row['repo']} {row['sha']} {subject(row)}")
        return
    path = args.input.with_name("state.json")
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report = render(rows, state)
    if args.output:
        args.output.write_text(report, encoding="utf-8", newline="\n")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
