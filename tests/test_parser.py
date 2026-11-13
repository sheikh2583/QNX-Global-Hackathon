from tracelens.ingest.traceprinter import parse_text

SAMPLE = """\
TRACEPRINTER version 1.02
 -- HEADER FILE INFORMATION --
       TRACE_FILE_NAME:: /dev/shmem/tracebuffer.kev
        CYCLES_PER_SEC:: 2000000000
 -- KERNEL EVENTS --
t:0xfffffff0 CPU:00 THREAD  :THRUNNING     pid:7 tid:2
t:0xfffffffa CPU:00 KER_CALL:SYNC_SEM_WAIT/105 sync:0x8040 try:0
t:0x00000010 CPU:01 INT_ENTR:0x00000009 (9)       IP:0xf008433e
t:0x00000020 CPU:00 USREVENT:EVENT:100 STR:TL_META name=control prio=50
t:0x00000030 CPU:00 PROCESS :PROCCREATE_NAME
                      ppid:1
                       pid:12291
                      name:./server
"""


def test_header_and_cycles():
    t = parse_text(SAMPLE)
    assert t.cycles_per_sec == 2_000_000_000
    assert t.header["TRACE_FILE_NAME"] == "/dev/shmem/tracebuffer.kev"
    assert len(t.events) == 5
    assert t.unparsed_lines == 0


def test_counter_wraparound_is_monotonic():
    t = parse_text(SAMPLE)
    times = [e.t_ns for e in t.events]
    assert times == sorted(times)
    # 0xfffffff0 -> 0x1_00000010 is 0x20 cycles = 16 ns at 2 GHz
    assert t.events[2].t_ns == 16


def test_kinds_and_args():
    t = parse_text(SAMPLE)
    run, call, irq, usr, proc = t.events
    assert (run.cls, run.kind, run.pid, run.tid) == ("THREAD", "RUNNING", 7, 2)
    assert (call.kind, call.args["sync"]) == ("SYNC_SEM_WAIT", "0x8040")
    assert irq.kind == "9"
    assert usr.text == "TL_META name=control prio=50"
    assert proc.args == {"ppid": "1", "pid": "12291", "name": "./server"}


def test_attribution_by_cpu():
    t = parse_text(SAMPLE)
    _, call, irq, usr, _ = t.events
    assert call.key == (7, 2)          # running on CPU 0
    assert usr.key == (7, 2)
    assert irq.key is None             # nothing seen running on CPU 1 yet
