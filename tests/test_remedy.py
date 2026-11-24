"""Deterministic remedies: right fix for each proven root cause, and no rewrite when unsafe."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tracelens.analyze import analyze_file
from tracelens.config import load_config
from tracelens.findings import Finding
from tracelens.remedy import csrc, plan

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "fixtures" / "real"
CFG = load_config(REAL / "tracelens.toml")


def zoo(name: str, reference: bool = False) -> dict[str, str]:
    p = ROOT / "bugzoo" / ("reference/" + name + ".c" if reference else name + "/main.c")
    return {"main.c": p.read_text(encoding="utf-8")}


@pytest.fixture(scope="module")
def real():
    names = ["z1_infusion_pump", "z2_brake_by_wire", "z3_sensor_fusion", "z4_camera_pipeline", "z5_motor_encoder"]
    return {n: analyze_file(REAL / f"{n}.txt.gz", CFG).findings for n in names}


def auto(remedies):
    return [r.rule for r in remedies if r.automatic]


def finding(kind, title, threads=(), **metrics):
    return Finding(kind=kind, severity="critical", title=title, summary="", t_start=0, t_end=1,
                   threads=list(threads), evidence=[], metrics=metrics, qnx_note="")


# --------------------------------------------------------------------- the bug zoo, from real traces
def test_z1_semaphore_becomes_priority_inheriting_mutex(real):
    rems, out = plan(real["z1_infusion_pump"], zoo("z1_infusion_pump"))
    assert auto(rems) == ["semaphore-as-lock"]
    c = out["main.c"]
    assert "sem_wait(&buf_lock)" not in c and c.count("pthread_mutex_lock(&buf_lock)") == 2
    assert "static pthread_mutex_t buf_lock;" in c and "PTHREAD_PRIO_INHERIT" in c
    assert "tracelens_pi_mutex_init(&buf_lock) != 0" in c and "pthread_mutex_destroy(&buf_lock)" in c


def test_z2_fixed_priority_flag_is_dropped(real):
    rems, out = plan(real["z2_brake_by_wire"], zoo("z2_brake_by_wire"))
    assert auto(rems) == ["fixed-priority-channel"]
    assert "ChannelCreate(0)" in out["main.c"] and "_NTO_CHF_FIXED_PRIORITY" not in out["main.c"].split("*/", 3)[-1]


def test_z3_deadlock_is_guided_with_the_send_sites(real):
    rems, out = plan(real["z3_sensor_fusion"], zoo("z3_sensor_fusion"))
    assert auto(rems) == [] and out == zoo("z3_sensor_fusion")
    r = next(r for r in rems if r.rule == "ipc-cycle")
    assert any("MsgSend(" in code for _, _, code in r.locations) and any("MsgSendPulse" in g for g in r.guidance)


def test_z4_private_work_leaves_the_critical_section(real):
    rems, out = plan(real["z4_camera_pipeline"], zoo("z4_camera_pipeline"))
    assert auto(rems) == ["shrink-critical-section"]
    body = out["main.c"]
    lock, spin, memcpy_ = (body.index("pthread_mutex_lock(&store_lock)"), body.index("tl_spin_us(1500)"),
                           body.index("memcpy(frame_store[id]"))
    assert spin < lock < memcpy_  # work before the lock, the shared copy still under it
    assert body.index("/* Demosaic") < body.index("memset(tile")  # comments travel with their code


def test_z5_interrupt_unmasked_first_and_work_deferred(real):
    rems, out = plan(real["z5_motor_encoder"], zoo("z5_motor_encoder"))
    assert auto(rems) == ["ist-defer-work"]
    c = out["main.c"]
    loop = c[c.index("while (tl_now_ns() < end)"):]
    loop = loop[:loop.index("tracelens_irq_worker_stop")]
    assert "recompute_velocity_profile" not in loop
    assert loop.index("InterruptUnmask(irq, id)") < loop.index("tracelens_irq_worker_kick()")
    # the worker body is defined after the function it calls, before main
    assert c.index("static void recompute_velocity_profile") < c.index("static void tracelens_irq_work") \
        < c.index("int main(")
    assert c.index("tracelens_irq_worker_start()") < c.index("while (tl_now_ns() < end)")


def test_reference_fixes_need_nothing(real):
    for name in ("z1_infusion_pump", "z2_brake_by_wire", "z4_camera_pipeline", "z5_motor_encoder"):
        rems, out = plan(real[name], zoo(name, reference=True))
        assert auto(rems) == [], name


def test_remedies_are_deterministic(real):
    a = plan(real["z5_motor_encoder"], zoo("z5_motor_encoder"))[1]
    b = plan(real["z5_motor_encoder"], zoo("z5_motor_encoder"))[1]
    assert a == b


# --------------------------------------------------------------------- refusing unsafe rewrites
SEM_SIGNAL = """#include <semaphore.h>
static sem_t ready;
void *producer(void *a) { sem_post(&ready); return a; }
void *consumer(void *a) { sem_wait(&ready); return a; }
int main(void) { sem_init(&ready, 0, 0); return 0; }
"""


def test_semaphore_used_as_signal_is_not_turned_into_a_mutex():
    f = finding("priority_inversion", "Priority inversion: c waited on p via a semaphore")
    rems, out = plan([f], {"main.c": SEM_SIGNAL})
    assert auto(rems) == [] and out["main.c"] == SEM_SIGNAL
    assert any("not used strictly as a lock" in n for n in rems[0].notes)


ALIAS = """#include <pthread.h>
#include <string.h>
static pthread_mutex_t lk = PTHREAD_MUTEX_INITIALIZER;
static char shared_buf[64];
void work(void)
{
    char *dst = shared_buf;
    pthread_mutex_lock(&lk);
    memset(dst, 0, 64);
    shared_buf[0] = 1;
    pthread_mutex_unlock(&lk);
}
"""


def test_pointer_into_shared_data_keeps_its_statement_under_the_lock():
    f = finding("mutex_contention", "Mutex contention hotspot at 0x1000", kernel_space=False)
    rems, out = plan([f], {"main.c": ALIAS})
    assert auto(rems) == [] and out["main.c"] == ALIAS  # dst aliases shared_buf: nothing may move


EARLY_EXIT = """#include <pthread.h>
static pthread_mutex_t lk = PTHREAD_MUTEX_INITIALIZER;
static int counter;
int step(int x)
{
    pthread_mutex_lock(&lk);
    if (x < 0)
        return -1;
    counter += x;
    pthread_mutex_unlock(&lk);
    return 0;
}
"""


def test_statements_that_leave_the_function_are_never_moved():
    f = finding("mutex_contention", "Mutex contention hotspot at 0x1000", kernel_space=False)
    rems, out = plan([f], {"main.c": EARLY_EXIT})
    assert out["main.c"] == EARLY_EXIT


IST_LOCAL = """#include <sys/neutrino.h>
static void process(int v) { (void)v; }
int main(void)
{
    int id = 0, value = 0;
    while (1) {
        InterruptWait(0, NULL);
        value++;
        process(value);
        InterruptUnmask(5, id);
    }
}
"""


def test_interrupt_work_using_locals_is_guided_not_moved():
    f = finding("irq_handler_overrun", "Interrupt handler overrun on IRQ 5")
    rems, out = plan([f], {"main.c": IST_LOCAL})
    assert auto(rems) == [] and any("locals" in n for n in rems[0].notes)


def test_kernel_mutex_contention_gets_no_remedy():
    f = finding("mutex_contention", "Kernel mutex contention at 0xffff8000 (inside procnto)", kernel_space=True)
    assert plan([f], {"main.c": ALIAS})[0] == []


# --------------------------------------------------------------------- the C helpers
def test_mask_hides_comments_and_strings_but_keeps_offsets():
    text = 'int a; /* sem_wait(&x) */ char *s = "sem_wait(&x)"; // sem_wait(&x)\n#define X sem_wait\nint b;'
    m = csrc.mask(text)
    assert len(m) == len(text) and "sem_wait" not in m and m.count("\n") == text.count("\n")


def test_statements_split_compound_statements():
    code = "{ if (a) { b(); } else c(); d(); for (;;) { e(); } int x[] = {1, 2}; }"
    m = csrc.mask(code)
    st = csrc.statements(m, 1, len(code) - 1)
    assert [code[s.start:s.end].split("(")[0].split()[0] for s in st] == ["if", "d", "for", "int"]


# --------------------------------------------------------------------- patched code compiles
@pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("gcc") is None,
                    reason="host stub check needs Linux gcc (POSIX headers)")
@pytest.mark.parametrize("name", ["z1_infusion_pump", "z2_brake_by_wire", "z4_camera_pipeline", "z5_motor_encoder"])
def test_patched_workload_compiles_against_qnx_stubs(real, name, tmp_path):
    _, out = plan(real[name], zoo(name))
    src = tmp_path / "main.c"
    src.write_text(out["main.c"], encoding="utf-8")
    cp = subprocess.run(["gcc", "-fsyntax-only", "-Wall", "-Wextra", "-Werror", "-std=gnu11", "-D_GNU_SOURCE",
                         f"-I{ROOT / 'bugzoo' / 'hostcheck'}", f"-I{ROOT / 'bugzoo' / 'common'}", str(src)],
                        capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr


def test_interrupt_worker_runs_below_every_interrupt_thread_and_outside_attach(real):
    rems, out = plan(real["z5_motor_encoder"], zoo("z5_motor_encoder"))
    c = out["main.c"]
    assert "#define TRACELENS_IRQ_WORKER_PRIO 20" in c and "virtio_pci0 irq 256 at 21" in c
    assert c.index("tracelens_irq_worker_start()") < c.index("InterruptAttachEvent(irq")
    assert c.index("InterruptDetach(id)") < c.index("tracelens_irq_worker_stop();")


# memcached 1.6.45 logger.c, reduced to the lines that matter (memcached/memcached#1348).
LOGGER = """\
#include <pthread.h>
static volatile int run = 1;
static int watchers = 0;
static pthread_mutex_t lk = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;

static void *logger_thread(void *arg) {
    while (run) {
        usleep(1000);
        pthread_mutex_lock(&lk);
        if (watchers == 0) {
            pthread_cond_wait(&cv, &lk);
        }
        pthread_mutex_unlock(&lk);
    }
    return NULL;
}

static int stop_logger_thread(void) {
    pthread_mutex_lock(&lk);
    run = 0;
    pthread_cond_signal(&cv);
    pthread_mutex_unlock(&lk);
    return 0;
}
"""


def _lost_wakeup_finding():
    from tracelens.findings import Finding
    return Finding(kind="lost_wakeup", severity="high", title="Lost wake-up", summary="", t_start=0, t_end=1,
                   threads=["mc-log"], id="TL-001")


def test_lost_wakeup_fix_rechecks_the_run_flag_under_the_lock():
    from tracelens.remedy import plan
    remedies, new = plan([_lost_wakeup_finding()], {"logger.c": LOGGER})
    assert [r.rule for r in remedies] == ["recheck-before-wait"] and remedies[0].automatic
    assert new["logger.c"] == LOGGER.replace("if (watchers == 0) {", "if ((watchers == 0) && run) {")


def test_lost_wakeup_fix_refuses_when_the_stopper_does_not_hold_the_lock():
    from tracelens.remedy import plan
    unlocked = LOGGER.replace("    pthread_mutex_lock(&lk);\n    run = 0;", "    run = 0;")
    remedies, new = plan([_lost_wakeup_finding()], {"logger.c": unlocked})
    assert not remedies[0].automatic and new["logger.c"] == unlocked


def test_lost_wakeup_fix_survives_a_file_it_cannot_parse():
    """memcached.c has braces that balance only after the preprocessor picks a branch."""
    from tracelens.remedy import plan
    odd = "#ifdef A\nvoid f(void) {\n#else\nvoid f(int x) {\n#endif\n  (void)0;\n}\n}\n"
    remedies, new = plan([_lost_wakeup_finding()], {"odd.c": odd, "logger.c": LOGGER})
    assert remedies[0].automatic and "&& run" in new["logger.c"]
