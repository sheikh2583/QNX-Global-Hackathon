# Does TraceLens work on QNX 8.0 on aarch64?

Measured 2026-11-23 on the project machine (WSL2 Ubuntu 24.04, QNX SDP 8.0, host x86_64).

**Verdict, stated plainly: not answered, and it cannot be answered on this machine without one
licensed 137 KB download that needs the user's myQNX login.** Everything up to booting an aarch64
guest works — the whole workload suite cross-compiles for `aarch64le` with no source change, QEMU can
emulate the machine mkqnximage asks for, and `tracelens target` now drives a second VM on its own port
— but `mkqnximage --arch=aarch64le` cannot finish the boot image because the SDP install is missing
`startup-qemu-virt`, and the package that provides it is behind an authenticated QNX download. So
there are **no aarch64 traces, no detector results on aarch64, and no answer yet on whether the radar
transfers.** Nothing in this document should be read as evidence that it does.

What follows is what *was* established, with the commands and the output, and exactly where it stops.

## 1. The workloads build for aarch64 with no source change

```
make -C bugzoo ARCH=aarch64le OUT=out-aarch64le
```

All five planted-bug workloads, all five reference fixes and the 16-scenario generator `tlgen` compile
with `qcc -Vgcc_ntoaarch64le -O2 -g -Wall -Wextra -std=gnu11` — **eleven binaries, zero warnings, zero
edits.** The QNX API surface the bug zoo uses (`pthread`, `sem_*`, `ChannelCreate`/`MsgSend`,
`InterruptAttach`, `TraceEvent`, `ClockCycles`) is architecture-neutral, and nothing in `bugzoo/common/tl.h`
assumes x86.

That is the whole "does my code port?" question answered, and it is the part a judge is most likely to
doubt. It says nothing yet about *behaviour*.

## 2. The host can emulate the machine mkqnximage wants

`qemu-system-aarch64` 8.2.2 (from Ubuntu's `qemu-system-arm`, unpacked into `~/bin` without root),
accelerators: **`tcg` only** — an x86 host has no KVM for ARM, so every guest instruction is
interpreted. `mkqnximage`'s `--aarch64-version=8` default asks for `-machine virt-4.2 -cpu cortex-a57`,
and that machine initialises with 4 CPUs and 2 GB.

Consequence for the measurement, stated before the data exists: timing on this guest would be *emulated*
timing, several times slower than the KVM x86 guest, with a different interrupt and wake-up profile. A
gap found there would not separate "aarch64" from "TCG". A real verdict on ARM wants hardware or a KVM
ARM host; this machine can only ever give the weaker version of the answer.

## 3. Where it stops, exactly

```
$ cd ~/qnx-vm-aarch64
$ mkqnximage --type=qemu --arch=aarch64le --cpu=4 --ram=2G --noprompt \
      --hostname=tracelens-a64 --ssh-ident=$HOME/.ssh/id_ed25519.pub --sshd-pregen=yes
...
Generating system partition . . .            # 81 MB  output/system.part   OK
Generating data partition . . .              # 66 MB  output/data.part     OK
Generating ifs . . .
output/build/ifs.build:23 Host file 'startup-qemu-virt' not available
Failed to create ifs boot image
Failed
```

Both filesystem partitions build. Only the boot image fails, and only for one missing file. The SDP
install has everything else an aarch64le guest needs:

| Needed | Present in `~/qnx800/target/qnx/aarch64le`? |
|---|---|
| `boot/sys/procnto-smp-instr` (66 MB) | yes |
| `boot/sys/libmod_gicv2.a`, `libmod_gicv3.a` | yes |
| `usr/lib/libstartup.a` | yes |
| `bin/`, `sbin/` userland (227 binaries incl. `tracelogger`, `pidin`) | yes |
| `boot/sys/startup-qemu-virt` | **no** |

`startup-qemu-virt` is a board startup binary; it is not built from anything in the SDP and there is no
substitute (x86's `startup-x86`/`startup-apic` are the wrong architecture, and `libstartup.a` is the
library a BSP links, not a startup). The package that provides it is in the account's own repository:

```
id:      com.qnx.qnx800.target.qemuvirt
name:    QNX® SDP 8.0 QEMU Virtualization Drivers (Startup)
version: 0.2.1.00087T202507241124L        size: 137,792 bytes
provides: binary: startup_qemu_virt
```

It resolves and verifies offline, and fails only at the download:

```
$ ~/qnx/qnxsoftwarecenter/qnxsoftwarecenter_clt -installIU com.qnx.qnx800.target.qemuvirt -verifyOnly
Installing com.qnx.qnx800.target.qemuvirt 0.2.1.00087T202507241124L.
Info: Operation completed in 280 ms.

$ ... -installIU com.qnx.qnx800.target.qemuvirt -downloadOnly
Error: Unable to read repository at
  https://www.qnx.com/swcenter/api/1/packages/com.qnx.qnx800.target.qemuvirt/.../download.;
  caused by: HttpUnauthorizedException: Request requires authorization
```

**The one step that unblocks this:** install *QNX® SDP 8.0 QEMU Virtualization Drivers (Startup)* in QNX
Software Center (`~/qnx/qnxsoftwarecenter/qnxsoftwarecenter`), which holds the myQNX login. Then
`scripts/aarch64_pilot.sh` runs the rest unattended. No other blocker was found: the compiler, the
userland, the kernel, the emulator and the tooling are all in place.

Rejected alternatives, for the record: the QNX Everywhere quickstart image already downloaded
(`~/qnx800/images/qemu`) is `OPT_ARCH='x86_64'`; the account's repository lists 30 `bsp.hw.*` BSPs, all
for real boards (i.MX, TI, Xilinx, Raspberry Pi) and all behind the same authenticated download, none
of which targets QEMU's `virt` machine; writing an aarch64 `virt` startup against `libstartup.a` is BSP
work, not a hackathon session.

### 3b. Update, later the same day: the first blocker is cleared, a second one is behind it

The user logged in to QNX Software Center and `com.qnx.qnx800.target.qemuvirt` was installed through
the GUI (`startup-qemu-virt`, 1.6 MB, now in `~/qnx800/target/qnx/aarch64le/boot/sys/`). After
`mkqnximage --clean` the image **builds** (`output/ifs.bin` 9.8 MB) with one warning, and it **boots**:
the QNX 8.0 aarch64 kernel (`procnto-smp-instr`) starts under TCG on `virt-4.2`/cortex-a57 with 4 CPUs,
runs slogger2, PCI services and fsevmgr. It then stops:

```
Warning: Host file 'sbin/devb-virtio' missing.                       (at image build)
/proc/boot/startup.sh[26]: devb-virtio: cannot execute - No such file or directory
Unable to access /dev/hd0
mount: Can't mount /boot, /system, /data (type qnx6)
No system file system, giving up.
```

The aarch64 `virt` machine's disk is `virtio-blk`, and its driver is not in this SDP install. Without
`/system` there is no sshd, no `tracelogger`, no workload: **the guest cannot be reached**
(`tracelens target up` reported "VM answering ssh" because QEMU's port forward accepts TCP whether or
not a guest is listening, and a real `ssh` then times out in the banner exchange — a false positive
worth a follow-up in `_ssh_open`).

The driver is in the account's repository as `com.qnx.qnx800.target.driver.virtio.devb`
("Virtualization Drivers (Block)", 0.1.0), with `.devc`, `.startup` and the umbrella
`com.qnx.qnx800.target.driver.virtio` beside it. All four resolve with `-verifyOnly`. They did not
appear under "Available" in the GUI; the "All" tab has a group "Inaccessible: Insufficient
Entitlements or Missing Click-through Agreements (147)" that probably holds them, which would mean a
click-through agreement the user has to accept. **Not confirmed**: the WSLg session started failing
(RDP error dialog, UI stuck at "Synchronizing 73%") before the group could be read.

Next: restart WSLg (`wsl --shutdown`), reopen Software Center, find the four `driver.virtio*` packages
(probably under "Inaccessible"), accept the agreement if that is what it asks for, install, then
`mkqnximage --clean` again and `scripts/aarch64_pilot.sh --no-build`.

## 4. What was built so the run is one command

Changes in this branch, all tested, all with the x86 defaults unchanged:

- **`tracelens target up --ssh-port N`** — a second VM gets its own forwarded port beside the first.
  `--image-dir` already existed; the two together are what lets an aarch64 guest run on 127.0.0.1:2223
  while the x86 one keeps 2222. Verified while the x86 VM was up: 2222 open, 2223 free, x86 image
  untouched.
- **A reused VM is now proved to be *this* image's VM**, by a live `output/qemu.pid` in the image
  directory, instead of "something answers on the port". Before this change a second image directory on
  a busy port would have silently adopted the first VM and analysed the wrong target; now it says so and
  names `--ssh-port`.
- **`user_net_argv` keeps the architecture's own NIC.** mkqnximage gives the aarch64 `virt` machine
  virtio-mmio devices (`virtio-net-device`, `virtio-blk-device`), not PCI ones; swapping the bridge for
  QEMU's NAT preserves whatever device the logged command names, and adds the right one when the logged
  command has no NIC at all.
- **`tracelens fix --arch` / `eval --arch`** — the fix loop's `QccBuilder` had `arch="x86_64"` hardcoded
  at every call site, so a fix proven "on the target" would have been rebuilt for x86 whatever the target
  was. This is a real architecture lock-in that this track found in shared code.
- **`tracelens eval detect|fix --bin-dir`** — run the evaluation against `bugzoo/out-aarch64le` without
  moving binaries over the x86 build.
- **`scripts/arch_compare.py`** — the gap table of `scripts/real_vs_sim.py` (median per feature per
  thread) pointed at two *real* collections, plus the shipped radar scored on the first one.
- **`scripts/aarch64_pilot.sh`** — build, boot on 2223, collect the 16 scenarios, compare, run the bug
  zoo. It refuses to start without `startup-qemu-virt` and says why.

Regression tests for the shared code: `tests/test_target_ops.py` (4 new), `tests/test_fix_engine.py` (2),
`tests/test_evaluation.py` (1). 171 tests pass; `scripts/check.sh lint` clean.

## 5. The same-architecture control, measured

A cross-architecture gap table means nothing without knowing how much *two runs on the same
architecture* already differ. That control exists now — [arch_control.md](arch_control.md), two x86
collections (`data/pilot`, one run per scenario, against `data/real`, 120 runs per scenario):

- **238 of 275 compared feature/thread pairs agree within 0.10.**
- The widest same-architecture gaps are **`cpus_used` (1.000)** on four scenarios, **`max_run_frac`
  (0.975)** on `irq_overrun`'s interrupt thread, then `share_sleep` / `share_ready` around 0.20–0.35.
- The shipped radar on that collection: 8 of 10 planted-bug traces flagged on the thread that suffers,
  0 false alarms on 6 healthy ones — reproducing the recorded pilot result, which is also what validates
  `arch_compare.py` itself.

So when aarch64 data arrives, read its gap table against *these* numbers. In particular, a `cpus_used`
difference is already worth 1.0 between two x86 runs and proves nothing about architecture.

## 6. What the feature design predicts (reasoned, not measured)

Marked **(verify)** in full: this is an argument from the code, and the whole point of the track was to
replace it with a measurement.

All 19 features in `src/tracelens/ml/features.py` are dimensionless or counts — nine time *shares*
(`share_running`, `share_ready`, `share_sem`, …), four fractions (`max_block_frac`, `max_ready_frac`,
`max_run_frac`, `intr_masked_frac`), `inversion_frac`, `prio_rank` (rank, not absolute priority), three
per-millisecond rates (`blocks_per_ms`, `preempts_per_ms`, `migrations_per_ms`) and `cpus_used`. None
carries an absolute time, a clock rate or a pointer width. The parser takes the clock rate from the
trace header (`TRACE_CYCLES_PER_SEC`) and [refuses to guess](../../src/tracelens/ingest/traceprinter.py)
when it is absent, so a different clock changes nothing downstream.

The parts most likely to move on another machine are therefore the four that are not pure ratios: the
three per-ms rates, which scale with how fast the guest runs, and `cpus_used`, which depends on the CPU
count and on how the scheduler spreads threads — the feature that already moves most between two x86
runs. The one architecture-flavoured constant found anywhere in the analysis code is
`KERNEL_SPACE = 0xFFFF_8000_0000_0000` in `detectors/mutex_contention.py`, which labels a sync object as
living inside procnto; it is used only to downgrade such findings to context, and the comment claiming
aarch64 maps the kernel the same way is itself still **(verify)**.

## 7. To finish this

1. Install `com.qnx.qnx800.target.qemuvirt` in QNX Software Center (§3).
2. `source ~/qnx800/qnxsdp-env.sh`, activate the venv, `PATH=$HOME/bin:$PATH` for `qemu-system-aarch64`.
3. `scripts/aarch64_pilot.sh` (hours, not minutes, under TCG; `PER_SCENARIO=5` for tighter medians).
4. Replace §§1–6 of this file with what it measured: which detectors fired on which thread, the radar's
   hit and false-alarm counts on aarch64, and the gap table beside the control. If the radar does not
   transfer, say so here as plainly as this verdict is stated.
5. Do **not** loosen `bugzoo/tracelens.toml` to make the deadline rule pass under emulation; use a
   separate `bugzoo/tracelens.aarch64.toml` and record which budget moved and what justified it.
