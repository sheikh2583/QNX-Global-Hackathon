# Concurrency bug-fix mining

Kept **3,220 commits** from **48 repositories**. **314 (9.8%)** have a reproducer hint. GitHub returned issue text for **261 of 764** commits with an issue reference.

**Uncovered share exceeds 40%. 2,279 commits (70.8%) are `other`.**

The miner searched the history reachable from each pinned default-branch tip. The repository table records progress if a scan stopped early. The file and line caps apply across the entire commit. The stored patch contains only C/C++ files and has three lines of context. Years come from each commit's author date. Licence IDs reflect current GitHub repository metadata.

Peak observed disk usage for the mining directory was **763,222,522 bytes**.

## Repositories

Checked 6,844 of 6,844 Git message candidates in 49 repositories.

| Repository | Kept | Candidates checked / found | Status |
| --- | --- | --- | --- |
| zephyrproject-rtos/zephyr | 775 | 1,454 / 1,454 | complete |
| apache/nuttx | 320 | 578 / 578 | complete |
| facebook/rocksdb | 266 | 599 / 599 | complete |
| haproxy/haproxy | 215 | 477 / 477 | complete |
| grpc/grpc | 214 | 512 / 512 | complete |
| facebook/folly | 206 | 386 / 386 | complete |
| openssl/openssl | 92 | 195 / 195 | complete |
| RIOT-OS/RIOT | 88 | 158 / 158 | complete |
| libuv/libuv | 77 | 148 / 148 | complete |
| RTEMS/rtems | 62 | 148 / 148 | complete |
| ARMmbed/mbed-os | 61 | 127 / 127 | complete |
| jemalloc/jemalloc | 60 | 102 / 102 | complete |
| sqlite/sqlite | 58 | 122 / 122 | complete |
| redis/redis | 49 | 200 / 200 | complete |
| lttng/lttng-ust | 47 | 69 / 69 | complete |
| libusb/libusb | 46 | 64 / 64 | complete |
| nanomsg/nng | 45 | 128 / 128 | complete |
| eProsima/Fast-DDS | 40 | 139 / 139 | complete |
| urcu/userspace-rcu | 35 | 59 / 59 | complete |
| memcached/memcached | 34 | 67 / 67 | complete |
| eclipse-cyclonedds/cyclonedds | 33 | 62 / 62 | complete |
| opencv/opencv | 33 | 79 / 79 | complete |
| RT-Thread/rt-thread | 29 | 48 / 48 | complete |
| scylladb/seastar | 29 | 103 / 103 | complete |
| ros2/rclcpp | 28 | 56 / 56 | complete |
| curl/curl | 27 | 166 / 166 | complete |
| libevent/libevent | 26 | 48 / 48 | complete |
| open62541/open62541 | 24 | 56 / 56 | complete |
| zeromq/libzmq | 24 | 72 / 72 | complete |
| boostorg/thread | 22 | 49 / 49 | complete |
| eclipse-iceoryx/iceoryx | 22 | 42 / 42 | complete |
| contiki-ng/contiki-ng | 15 | 45 / 45 | complete |
| FreeRTOS/FreeRTOS-Kernel | 14 | 24 / 24 | complete |
| eclipse-zenoh/zenoh-pico | 12 | 27 / 27 | complete |
| nginx/nginx | 12 | 43 / 43 | complete |
| microsoft/mimalloc | 11 | 19 / 19 | complete |
| nanomsg/nanomsg | 11 | 19 / 19 | complete |
| oneapi-src/oneTBB | 11 | 29 / 29 | complete |
| civetweb/civetweb | 9 | 13 / 13 | complete |
| eclipse-paho/paho.mqtt.c | 9 | 13 / 13 | complete |
| concurrencykit/ck | 8 | 12 / 12 | complete |
| boostorg/asio | 6 | 24 / 24 | complete |
| eclipse-mosquitto/mosquitto | 6 | 14 / 14 | complete |
| eclipse-threadx/threadx | 3 | 24 / 24 | complete |
| libssh2/libssh2 | 2 | 10 / 10 | complete |
| redis/hiredis | 2 | 3 / 3 | complete |
| eclipse-threadx/netxduo | 1 | 10 / 10 | complete |
| OpenAMP/open-amp | 1 | 1 / 1 | complete |
| qnx-ports/build-files | 0 | 1 / 1 | complete |

Rejections by first applicable check.

| Check | Commits |
| --- | --- |
| file limit | 826 |
| line limit | 116 |
| message | 1871 |
| no production source | 811 |

## Author years

| Year | Kept |
| --- | --- |
| 1995 | 2 |
| 1996 | 2 |
| 1997 | 1 |
| 1999 | 2 |
| 2000 | 4 |
| 2001 | 2 |
| 2002 | 4 |
| 2003 | 1 |
| 2004 | 2 |
| 2005 | 1 |
| 2006 | 1 |
| 2007 | 7 |
| 2008 | 17 |
| 2009 | 24 |
| 2010 | 38 |
| 2011 | 50 |
| 2012 | 55 |
| 2013 | 86 |
| 2014 | 95 |
| 2015 | 159 |
| 2016 | 164 |
| 2017 | 186 |
| 2018 | 178 |
| 2019 | 212 |
| 2020 | 203 |
| 2021 | 217 |
| 2022 | 229 |
| 2023 | 247 |
| 2024 | 261 |
| 2025 | 288 |
| 2026 | 482 |

<details><summary>Year counts by repository</summary>

| Repository | Author year (kept commits) |
| --- | --- |
| apache/nuttx | 2007 (2), 2008 (4), 2009 (2), 2011 (3), 2012 (3), 2013 (7), 2014 (1), 2015 (9), 2016 (8), 2017 (13), 2018 (7), 2019 (13), 2020 (18), 2021 (11), 2022 (31), 2023 (35), 2024 (34), 2025 (59), 2026 (60) |
| ARMmbed/mbed-os | 2013 (1), 2014 (1), 2015 (3), 2016 (9), 2017 (12), 2018 (19), 2019 (13), 2020 (3) |
| boostorg/asio | 2008 (1), 2011 (1), 2012 (1), 2013 (1), 2019 (1), 2021 (1) |
| boostorg/thread | 2001 (1), 2004 (1), 2008 (3), 2010 (3), 2012 (1), 2013 (2), 2016 (1), 2017 (10) |
| civetweb/civetweb | 2010 (1), 2011 (1), 2013 (2), 2015 (1), 2016 (2), 2018 (1), 2020 (1) |
| concurrencykit/ck | 2012 (2), 2013 (2), 2014 (1), 2018 (2), 2026 (1) |
| contiki-ng/contiki-ng | 2009 (1), 2011 (2), 2013 (1), 2015 (1), 2016 (2), 2017 (1), 2020 (1), 2023 (1), 2026 (5) |
| curl/curl | 2008 (1), 2010 (1), 2011 (1), 2014 (2), 2015 (2), 2016 (2), 2017 (1), 2018 (1), 2020 (1), 2021 (3), 2023 (3), 2024 (1), 2025 (5), 2026 (3) |
| eclipse-cyclonedds/cyclonedds | 2018 (2), 2019 (12), 2020 (5), 2021 (3), 2022 (3), 2023 (3), 2024 (3), 2025 (2) |
| eclipse-iceoryx/iceoryx | 2020 (12), 2021 (5), 2022 (2), 2023 (1), 2024 (1), 2025 (1) |
| eclipse-mosquitto/mosquitto | 2014 (3), 2020 (1), 2022 (1), 2025 (1) |
| eclipse-paho/paho.mqtt.c | 2013 (1), 2015 (1), 2018 (1), 2019 (1), 2020 (2), 2022 (1), 2023 (1), 2025 (1) |
| eclipse-threadx/netxduo | 2026 (1) |
| eclipse-threadx/threadx | 2026 (3) |
| eclipse-zenoh/zenoh-pico | 2021 (2), 2022 (1), 2023 (1), 2024 (4), 2025 (3), 2026 (1) |
| eProsima/Fast-DDS | 2015 (6), 2016 (7), 2017 (1), 2018 (1), 2019 (5), 2020 (4), 2021 (3), 2022 (5), 2023 (3), 2024 (3), 2025 (2) |
| facebook/folly | 2012 (1), 2013 (3), 2014 (21), 2015 (16), 2016 (11), 2017 (13), 2018 (16), 2019 (15), 2020 (19), 2021 (18), 2022 (15), 2023 (11), 2024 (11), 2025 (14), 2026 (22) |
| facebook/rocksdb | 2011 (1), 2012 (1), 2013 (6), 2014 (11), 2015 (17), 2016 (19), 2017 (16), 2018 (20), 2019 (18), 2020 (21), 2021 (25), 2022 (29), 2023 (14), 2024 (17), 2025 (18), 2026 (33) |
| FreeRTOS/FreeRTOS-Kernel | 2008 (2), 2019 (1), 2020 (3), 2021 (2), 2023 (1), 2024 (2), 2025 (2), 2026 (1) |
| grpc/grpc | 2014 (1), 2015 (39), 2016 (28), 2017 (29), 2018 (9), 2019 (11), 2020 (6), 2021 (8), 2022 (9), 2023 (14), 2024 (23), 2025 (20), 2026 (17) |
| haproxy/haproxy | 2009 (2), 2012 (3), 2013 (2), 2014 (1), 2016 (3), 2017 (8), 2018 (9), 2019 (36), 2020 (10), 2021 (20), 2022 (17), 2023 (28), 2024 (32), 2025 (25), 2026 (19) |
| jemalloc/jemalloc | 2010 (5), 2011 (4), 2012 (5), 2013 (5), 2014 (8), 2015 (2), 2016 (6), 2017 (12), 2018 (2), 2019 (2), 2020 (1), 2023 (1), 2024 (3), 2026 (4) |
| libevent/libevent | 2009 (5), 2010 (8), 2011 (1), 2014 (3), 2017 (1), 2018 (3), 2019 (1), 2020 (1), 2021 (2), 2026 (1) |
| libssh2/libssh2 | 2026 (2) |
| libusb/libusb | 2008 (1), 2009 (2), 2010 (2), 2011 (5), 2012 (1), 2013 (11), 2014 (3), 2015 (1), 2016 (3), 2017 (1), 2018 (1), 2019 (1), 2020 (3), 2021 (1), 2022 (2), 2023 (2), 2024 (1), 2026 (5) |
| libuv/libuv | 2011 (1), 2012 (4), 2013 (11), 2014 (1), 2015 (8), 2016 (3), 2017 (3), 2018 (13), 2019 (3), 2020 (5), 2021 (2), 2022 (6), 2023 (6), 2024 (3), 2025 (3), 2026 (5) |
| lttng/lttng-ust | 2009 (1), 2010 (2), 2011 (8), 2012 (7), 2013 (8), 2014 (3), 2015 (2), 2016 (4), 2017 (1), 2018 (1), 2019 (5), 2020 (1), 2022 (2), 2023 (1), 2026 (1) |
| memcached/memcached | 2011 (5), 2012 (4), 2014 (1), 2017 (2), 2018 (3), 2019 (5), 2020 (2), 2022 (3), 2023 (6), 2024 (1), 2026 (2) |
| microsoft/mimalloc | 2019 (3), 2021 (1), 2024 (1), 2025 (1), 2026 (5) |
| nanomsg/nanomsg | 2012 (2), 2013 (4), 2014 (1), 2015 (1), 2016 (3) |
| nanomsg/nng | 2016 (2), 2017 (19), 2018 (6), 2020 (2), 2021 (1), 2023 (2), 2024 (10), 2025 (1), 2026 (2) |
| nginx/nginx | 2010 (1), 2012 (1), 2014 (1), 2015 (2), 2016 (2), 2017 (1), 2018 (2), 2022 (1), 2023 (1) |
| oneapi-src/oneTBB | 2021 (2), 2022 (2), 2023 (1), 2024 (2), 2025 (1), 2026 (3) |
| open62541/open62541 | 2015 (1), 2017 (2), 2019 (1), 2022 (6), 2023 (2), 2024 (1), 2025 (2), 2026 (9) |
| OpenAMP/open-amp | 2016 (1) |
| opencv/opencv | 2012 (2), 2013 (1), 2014 (1), 2015 (7), 2016 (1), 2017 (1), 2018 (6), 2019 (1), 2021 (2), 2022 (1), 2023 (2), 2024 (1), 2025 (1), 2026 (6) |
| openssl/openssl | 1999 (2), 2000 (3), 2001 (1), 2002 (1), 2004 (1), 2011 (1), 2012 (4), 2014 (1), 2015 (1), 2016 (7), 2017 (3), 2018 (4), 2019 (7), 2020 (2), 2021 (14), 2023 (4), 2024 (8), 2025 (10), 2026 (18) |
| redis/hiredis | 2015 (1), 2018 (1) |
| redis/redis | 2009 (1), 2010 (4), 2011 (4), 2013 (3), 2014 (3), 2015 (1), 2016 (2), 2017 (3), 2018 (2), 2019 (1), 2020 (2), 2021 (3), 2022 (3), 2023 (4), 2024 (3), 2025 (3), 2026 (7) |
| RIOT-OS/RIOT | 2010 (1), 2011 (1), 2013 (4), 2014 (9), 2015 (6), 2016 (5), 2017 (4), 2018 (3), 2019 (8), 2020 (10), 2021 (8), 2022 (7), 2023 (3), 2024 (6), 2025 (5), 2026 (8) |
| ros2/rclcpp | 2015 (2), 2017 (2), 2019 (2), 2020 (3), 2021 (5), 2022 (1), 2023 (3), 2024 (2), 2025 (2), 2026 (6) |
| RT-Thread/rt-thread | 2009 (1), 2013 (3), 2014 (3), 2016 (1), 2020 (2), 2021 (1), 2022 (3), 2023 (4), 2024 (4), 2025 (3), 2026 (4) |
| RTEMS/rtems | 1995 (2), 1996 (2), 1997 (1), 2000 (1), 2002 (3), 2003 (1), 2005 (1), 2008 (1), 2011 (1), 2012 (4), 2013 (4), 2014 (9), 2015 (9), 2016 (8), 2017 (2), 2018 (2), 2020 (2), 2021 (1), 2024 (1), 2025 (2), 2026 (5) |
| scylladb/seastar | 2014 (1), 2015 (1), 2016 (3), 2017 (1), 2018 (2), 2019 (2), 2020 (3), 2021 (4), 2022 (2), 2023 (3), 2024 (3), 2025 (2), 2026 (2) |
| sqlite/sqlite | 2006 (1), 2007 (5), 2008 (4), 2009 (4), 2010 (7), 2011 (3), 2012 (1), 2014 (2), 2015 (5), 2016 (1), 2017 (4), 2018 (3), 2019 (1), 2021 (2), 2022 (1), 2023 (7), 2024 (2), 2025 (3), 2026 (2) |
| urcu/userspace-rcu | 2009 (5), 2011 (5), 2012 (2), 2013 (1), 2014 (2), 2015 (4), 2016 (1), 2019 (1), 2020 (1), 2022 (6), 2023 (2), 2025 (1), 2026 (4) |
| zephyrproject-rtos/zephyr | 2015 (10), 2016 (15), 2017 (19), 2018 (34), 2019 (42), 2020 (55), 2021 (66), 2022 (69), 2023 (77), 2024 (78), 2025 (95), 2026 (215) |
| zeromq/libzmq | 2010 (3), 2011 (2), 2012 (6), 2013 (3), 2014 (1), 2016 (4), 2017 (1), 2018 (2), 2020 (1), 2021 (1) |

</details>

## Licence mix

| SPDX ID | Commits |
| --- | --- |
| Apache-2.0 | 1799 |
| BSD-2-Clause | 12 |
| BSD-3-Clause | 53 |
| GPL-2.0 | 266 |
| LGPL-2.1 | 134 |
| MIT | 151 |
| MPL-2.0 | 48 |
| No SPDX ID | 757 |

## Fix shapes

A commit can receive several shape labels. `other` is exclusive. Median size counts inserted and deleted C/C++ lines in the stored patch. Each sample is drawn without replacement with seed 20261125. Shapes with fewer than 20 matches show every match.

| Shape | Commits | Repos | Median changed C/C++ lines |
| --- | --- | --- | --- |
| `add-predicate-loop` | 19 | 11 | 41 |
| `check-flag-before-wait` | 7 | 5 | 24 |
| `lock-order` | 18 | 9 | 31 |
| `move-work-out-of-lock` | 70 | 24 | 38.5 |
| `add-lock` | 369 | 33 | 33 |
| `remove-lock` | 112 | 23 | 43.5 |
| `use-trylock-or-timeout` | 25 | 12 | 65 |
| `sem-to-mutex` | 6 | 2 | 57 |
| `priority-inheritance` | 1 | 1 | 52 |
| `signal-under-lock` | 3 | 3 | 48 |
| `signal-outside-lock` | 4 | 4 | 76 |
| `signal-to-broadcast` | 1 | 1 | 5 |
| `atomic-or-volatile` | 235 | 34 | 43 |
| `add-cancel-or-shutdown-path` | 97 | 20 | 64 |
| `async-signal-safety` | 0 | 0 | — |
| `complete-unlock-on-exit` | 81 | 25 | 17 |
| `mask-interrupts-around-state` | 73 | 5 | 34 |
| `change-lock-target` | 23 | 13 | 55 |
| `retain-object-until-work-finishes` | 2 | 2 | 87.5 |
| `serialize-work-on-owner-queue` | 5 | 1 | 24 |
| `other` | 2279 | 47 | 15 |

## Template priorities

Ranked by the specificity of the source edit, spread across repositories, and strength of the before-and-after trace evidence. The counts are heuristic matches. The proposed trace checks and template preconditions are **(verify)** on QNX.

| Rank | Shape | Commits / repos | Rewrite and verification |
| --- | --- | --- | --- |
| 1 | `complete-unlock-on-exit` | 81 / 25 | When a branch exits with a mutex it acquired and still owns, reuse the existing cleanup path or insert the matching unlock. Prove ownership on that branch and exercise the failure path. The trace can show an existing waiter acquire the mutex after the failure. |
| 2 | `lock-order` | 18 / 9 | Reorder two known acquisitions to follow an order already established in the program. Limit the rewrite to paths where neither acquisition depends on work under the other lock. A workload that reproduces a wait-for cycle gives the verifier a direct check. |
| 3 | `move-work-out-of-lock` | 70 / 24 | Extend the existing critical-section shrinker to narrow eligible RAII scopes and move work that uses an immutable snapshot. Check lock hold time, blocked peers, and the output of the moved operation. |
| 4 | `add-predicate-loop` | 19 / 11 | Reuse the existing predicate and mutex to replace a one-shot condition check with a wait loop. Exercise both a useful wake-up and an extra wake-up. The kernel trace shows wake and re-block transitions. A workload assertion checks the predicate and the resulting state. |
| 5 | `add-lock` | 369 / 33 | Start with a short access to a field already guarded by a known mutex elsewhere in the program. Check that the new acquisition follows the lock order. The trace can measure contention and progress. Use a workload assertion or a race detector to check shared-state correctness. |

`atomic-or-volatile` has broad project coverage. Its correctness depends on memory ordering and object lifetime, so this corpus gives stronger template evidence when a repair also has a directly observable wait or progress outcome. The shutdown label spans several different cancellation and wake-up protocols.

## Manual audit of 30 initially unclassified commits

I drew a separate sample from `other` after the history recheck and before the last rule refinements. I read the messages and changed lines using seed `20261125` and salt `manual-audit`. The review exposed three recurring gaps. Release paths often redirect to existing cleanup, lifetime fixes retain an object until in-flight work finishes, and queue serialization moves related work onto the same owner queue. The final rules detect the directly visible versions of those edits. The queue rule identifies five commits in one repository, so its portability is **(verify)**.

The sample also exposed an explicit documentation-only commit. I tightened the message filter and removed two such rows. Earlier fixes to the miner constrained hang-only matches to messages that name synchronization and excluded test-suite paths. The sample below preserves the audited commits, including rows whose disposition changed.

1. Add teardown for the work queue's mutex and use a lighter temporary queue. [urcu/userspace-rcu `ee0dc6541cf8`](https://github.com/urcu/userspace-rcu/commit/ee0dc6541cf8e2566c5f6056599c218ef7410720)
2. Build HCI parameters in local storage to avoid holding a scarce command buffer across allocation. [zephyrproject-rtos/zephyr `68f6b59e2d5c`](https://github.com/zephyrproject-rtos/zephyr/commit/68f6b59e2d5ccc4a0e8feba85d69fb8b08f4667c)
3. Represent the proxy bit as a state in an existing atomic lifecycle field. [oneapi-src/oneTBB `84efdd2a8768`](https://github.com/oneapi-src/oneTBB/commit/84efdd2a87684e3ed531832700f55525121b41ad)
4. Reduce work under the database mutex by checking candidate files directly. [facebook/rocksdb `356f8c5d8168`](https://github.com/facebook/rocksdb/commit/356f8c5d81686f9d85ddf4874300de0d2596ec4c)
5. Take a stable snapshot of I²C message descriptors for validation and transfer. [zephyrproject-rtos/zephyr `25fb83c6e0a4`](https://github.com/zephyrproject-rtos/zephyr/commit/25fb83c6e0a4ff0a357d97539c3b795e951280d0)
6. Preserve pending signal counts and adjust queue removal during reinitialization. [libevent/libevent `ed7e0e77ed57`](https://github.com/libevent/libevent/commit/ed7e0e77ed573d9f5b4123d7874de3efb02763d1)
7. Save and restore interrupt-controller state across suspend. Race classification remains **(verify)**. [zephyrproject-rtos/zephyr `43d08bd8bc8e`](https://github.com/zephyrproject-rtos/zephyr/commit/43d08bd8bc8ec5a23016805635b69c9c2e8b955b)
8. Move related client work and retry timers onto the same queue. [zephyrproject-rtos/zephyr `9fa82f0d8d29`](https://github.com/zephyrproject-rtos/zephyr/commit/9fa82f0d8d29d1f808829e16c09bb3942f53aa3b)
9. Publish the new options-file number under the database mutex. [facebook/rocksdb `349542332a8f`](https://github.com/facebook/rocksdb/commit/349542332a8fbfef3bcc9f6ace013919f2becd98)
10. Correct a code example in a header comment. Excluded from the final corpus. [RIOT-OS/RIOT `472d6d0abc0f`](https://github.com/RIOT-OS/RIOT/commit/472d6d0abc0ff7387f73dcd7efb3d6794ebb2a4b)
11. Swap callbacks out of the protected list and invoke them after releasing its lock. [facebook/folly `272a2e9a43c8`](https://github.com/facebook/folly/commit/272a2e9a43c84d2fbef02ce078224ab9af88cff0)
12. Change DNS lock ownership between a caller and its helper. [libevent/libevent `2df1f82bfa1b`](https://github.com/libevent/libevent/commit/2df1f82bfa1b432a277b0e1f8fc65aed7898f5e5)
13. Acquire a USB host guard during device registration. [ARMmbed/mbed-os `edbba136409d`](https://github.com/ARMmbed/mbed-os/commit/edbba136409def817d6f1351d8b8ddd8c521f6dc)
14. Widen the IRQ-masked region over a complete terminal refill state transition. [RTEMS/rtems `7338299c9628`](https://github.com/RTEMS/rtems/commit/7338299c962812df21d68b409e7e28a458b4a9d9)
15. Honor the configured priority-inheritance default when initializing mutexes. [apache/nuttx `06d00b4c8876`](https://github.com/apache/nuttx/commit/06d00b4c88764c8ee60e95f6e6cb44be0589e0d0)
16. Teach mutex unlock to handle the reset state. [apache/nuttx `02a9e76f7335`](https://github.com/apache/nuttx/commit/02a9e76f7335a79a31d44d7025b9f8a418bf753d)
17. Hold a reference to the selected version while reading its table properties. [facebook/rocksdb `6b3c71f6ed40`](https://github.com/facebook/rocksdb/commit/6b3c71f6ed40236b33d1fc3cf3db7b99a29f87eb)
18. Separate connection setup results and event handling by stream state. [haproxy/haproxy `d66ed88a7848`](https://github.com/haproxy/haproxy/commit/d66ed88a784880e84e91d848beb623bfc72ea83f)
19. Change cache-handle state and metadata management in a threading use-after-free fix. [facebook/rocksdb `3b981eaa1d97`](https://github.com/facebook/rocksdb/commit/3b981eaa1d97e90d9f9a33295551a3c83cc82988)
20. Remove an unnecessary thread-queue critical-section transition on SMP. [RTEMS/rtems `41814fa648e2`](https://github.com/RTEMS/rtems/commit/41814fa648e2c8ab3fb2359e4617657e74590b38)
21. Mark the pipeline done, wake workers, and drain it if the producer throws. [facebook/folly `9c527b540ca1`](https://github.com/facebook/folly/commit/9c527b540ca15e462d3ef89d283dcc1b64250540)
22. Narrow Wi-Fi lock ownership around hooks that take another lock. [apache/nuttx `d656cfa9302b`](https://github.com/apache/nuttx/commit/d656cfa9302bf2539fb2fb3d548db2b8da44f4ff)
23. Defer poll notification to a worker so a mutex-taking callback runs in thread context. [apache/nuttx `e8c6eb0aba5c`](https://github.com/apache/nuttx/commit/e8c6eb0aba5c8aceb395654e5243f4185d933f4d)
24. Restore an omitted async unblock on an error path. [openssl/openssl `e4b16013e9b3`](https://github.com/openssl/openssl/commit/e4b16013e9b3d19241d3ba0bb0875f0d70d93509)
25. Copy the file entry out before closing it and handle self-duplication. [apache/nuttx `42388f16e90e`](https://github.com/apache/nuttx/commit/42388f16e90e40ff3fb4e154eb2992879f52a069)
26. Extend a loader-time allocation exception to additional BSD systems. [microsoft/mimalloc `41ef691292ca`](https://github.com/microsoft/mimalloc/commit/41ef691292caa2417ef7e954f8eb9db2b18d1031)
27. Route a successful DHCP lease exit through the existing mutex cleanup. [zephyrproject-rtos/zephyr `e83d8d957dac`](https://github.com/zephyrproject-rtos/zephyr/commit/e83d8d957dac519cf0715ffa9def4777ba8b0734)
28. Rework the initialize, register, and deregister lifecycle for IPC endpoints. [zephyrproject-rtos/zephyr `5143db540cd6`](https://github.com/zephyrproject-rtos/zephyr/commit/5143db540cd65377a17444f28d498addab5dece9)
29. Normalize an exact-boundary nanosecond timeout and check the clock call. [zeromq/libzmq `fb852fd3e712`](https://github.com/zeromq/libzmq/commit/fb852fd3e712ef26cf67a5b4ee4e85b7eb4affba)
30. Change the const API of a shared promise. The concurrency impact of this edit is **(verify)**. [facebook/folly `547f5abfb80f`](https://github.com/facebook/folly/commit/547f5abfb80f37bd09f3cd4ffde82e8796c2b624)

The sample includes fixes that need API semantics or a larger control-flow window. Examples include callback execution after a wrapper-managed lock, cleanup labels outside the patch context, timeout normalization, and interrupt-to-worker deferral. These edits help explain why the uncovered share remains high after adding rules.

## Collection method and limits

- The 49 scans cover the 30 starting repositories plus 19 additional public C/C++ projects. QNX Ports' `build-files` repository contributed zero matches. The gRPC selection required a production C/C++ path under `src/core/` or `include/grpc/`. The pinned tips and per-stage counts are in `data/bugfix/state.json`.
- The miner uses a blobless clone without a checkout, Git message searches, tree-level path screening, and `git show` for line counts and patches. It fetches eligible blobs in batches and deletes each clone after processing. Renames count as deletes plus adds. Binary changes are excluded when Git cannot provide a line count. [Git clone documentation](https://git-scm.com/docs/git-clone), [Git show documentation](https://git-scm.com/docs/git-show)
- The miner queried issue titles, issue bodies, and current repository SPDX IDs through the existing `gh` login. It stores up to 3,000 body characters from the first local `#number` reference. Pull request references, unavailable issues, and missing references give a null issue text. A missing SPDX value includes GitHub's `NOASSERTION`. Historical and per-file licence terms are **(verify)**. [GitHub CLI API documentation](https://cli.github.com/manual/gh_api)
- Message and path filters give an approximate concurrency-fix corpus. Keyword-free fixes, fixes outside the pinned histories, and fixes over either size cap are outside the sample. Zephyr supplied 775 of the retained commits, so counts reflect repository selection and message conventions. Heuristics use API names, hunk order, and changed-line counts. Lock ownership, race freedom, and the correctness of individual labels require review **(verify)**.
- A reproducer hint records a code block or stack trace pattern in the message or retrieved issue text. Whether that text contains a working reproducer is **(verify)**. One retained patch contained a byte sequence represented by the UTF-8 replacement character.
- The first pass hit Windows' read-only Git pack files and an object-fetch error. The miner resumed after both fixes and the later filter recheck completed all pinned scans. Both the JSONL and the resume state are gitignored.

Run `.venv\Scripts\python.exe scripts/mine_bugfix.py` from the repository root to resume. Run `.venv\Scripts\python.exe scripts/bugfix_shapes.py` to regenerate the measured sections. `--sample-other 30` draws a 30-commit audit sample with the current rules.

## Random examples

<details><summary>add-predicate-loop (19 examples)</summary>

- Fix Coverity Scan #1619415 [eclipse-mosquitto/mosquitto `422ea6ed26b184917c9034e10eccf8e7c77d1b50`](https://github.com/eclipse-mosquitto/mosquitto/commit/422ea6ed26b184917c9034e10eccf8e7c77d1b50)
- Simplify GenericRateLimiter algorithm (#8602) [facebook/rocksdb `82b81dc8b5e5370d1c77c860da9b518b5a7681ad`](https://github.com/facebook/rocksdb/commit/82b81dc8b5e5370d1c77c860da9b518b5a7681ad)
- Fix ddsi_xpack_send blocking on full send queue [eclipse-cyclonedds/cyclonedds `b4753700e09789346b83e5b0305a09fbec4dfc10`](https://github.com/eclipse-cyclonedds/cyclonedds/commit/b4753700e09789346b83e5b0305a09fbec4dfc10)
- Fix: compat_futex_noasync race condition [urcu/userspace-rcu `db21eff94739900b1ab51d231dfb281ead0a0fa5`](https://github.com/urcu/userspace-rcu/commit/db21eff94739900b1ab51d231dfb281ead0a0fa5)
- Fix: urcu-qsbr: futex wait: handle spurious futex wakeups [urcu/userspace-rcu `4974ad5f21d2cb17d313504f8d1252738526d588`](https://github.com/urcu/userspace-rcu/commit/4974ad5f21d2cb17d313504f8d1252738526d588)
- Threading fixes [grpc/grpc `084c8089a4ca3f9e1a5516751a9562b902926f3b`](https://github.com/grpc/grpc/commit/084c8089a4ca3f9e1a5516751a9562b902926f3b)
- Fix: urcu-wait: futex wait: handle spurious futex wakeups [urcu/userspace-rcu `71693131550753be0fcd2b2d4175b53c697be5a3`](https://github.com/urcu/userspace-rcu/commit/71693131550753be0fcd2b2d4175b53c697be5a3)
- unix: work around glibc semaphore race condition [libuv/libuv `fbd6de31be38ba362daa56ccfd5be2a8f5d3b2b1`](https://github.com/libuv/libuv/commit/fbd6de31be38ba362daa56ccfd5be2a8f5d3b2b1)
- arch/sim: Use pthread_cond for signalling CPU initialisation done [apache/nuttx `5beb32bf0b1a9373f6a26a797e495757a2422e31`](https://github.com/apache/nuttx/commit/5beb32bf0b1a9373f6a26a797e495757a2422e31)
- Fix: urcu: futex wait: handle spurious futex wakeups [urcu/userspace-rcu `a18d0428065b301086d4e8a85bc057dc39946891`](https://github.com/urcu/userspace-rcu/commit/a18d0428065b301086d4e8a85bc057dc39946891)
- Fix: defer_rcu: futex wait: handle spurious futex wakeups [urcu/userspace-rcu `879a3e166178d16b2ffedc73899904d52285cfe8`](https://github.com/urcu/userspace-rcu/commit/879a3e166178d16b2ffedc73899904d52285cfe8)
- tls: Fix race/unhandled case in reloadable_certificates [scylladb/seastar `9010bae849769b03e0edeaafd12fc5fec8dc46e7`](https://github.com/scylladb/seastar/commit/9010bae849769b03e0edeaafd12fc5fec8dc46e7)
- epoll: fixes for races and early wakeups [nanomsg/nng `1514a532617b1fa7d4568a79a9d8ae24ceba1be9`](https://github.com/nanomsg/nng/commit/1514a532617b1fa7d4568a79a9d8ae24ceba1be9)
- sync with upstream @21706995 [facebook/rocksdb `80e5b0d944b7651046f8b0e795065eca02a01e59`](https://github.com/facebook/rocksdb/commit/80e5b0d944b7651046f8b0e795065eca02a01e59)
- Fix: call_rcu: futex wait: handle spurious futex wakeups [urcu/userspace-rcu `98d705dd32be11b3f134b5aed87f9c201c028c10`](https://github.com/urcu/userspace-rcu/commit/98d705dd32be11b3f134b5aed87f9c201c028c10)
- Bluetooth: HCI: h4: Fix RX buffer race between rx_thread and the ISR [zephyrproject-rtos/zephyr `a6a701e8828265874a00008162a42c55792d43ee`](https://github.com/zephyrproject-rtos/zephyr/commit/a6a701e8828265874a00008162a42c55792d43ee)
- add per node mutex for emulated futex [facebook/folly `8961aec70edc04d3e9f43fb28cc73d084896d8e1`](https://github.com/facebook/folly/commit/8961aec70edc04d3e9f43fb28cc73d084896d8e1)
- Fix: workqueue: futex wait: handle spurious futex wakeups [urcu/userspace-rcu `80c34c2de3d970eb82049798357743cfa71e8b54`](https://github.com/urcu/userspace-rcu/commit/80c34c2de3d970eb82049798357743cfa71e8b54)
- Fix several races [grpc/grpc `ba550da853b9e036ff29c5260c8f17ec4c03fc02`](https://github.com/grpc/grpc/commit/ba550da853b9e036ff29c5260c8f17ec4c03fc02)

</details>

<details><summary>check-flag-before-wait (7 examples)</summary>

- net: sockets: Add locking to receive callback [zephyrproject-rtos/zephyr `1184089d546f94ea3a88626ca9ba03b846d06adb`](https://github.com/zephyrproject-rtos/zephyr/commit/1184089d546f94ea3a88626ca9ba03b846d06adb)
- fix race in server shutdown [grpc/grpc `eab5c3355dc11ffe8f20747ef2d60af36601c5f3`](https://github.com/grpc/grpc/commit/eab5c3355dc11ffe8f20747ef2d60af36601c5f3)
- Fix checkpoint file deletion race with avoid_unnecessary_blocking_io (#7369) [facebook/rocksdb `92639b93a67c7ec28fd7d2de611eac759120ffce`](https://github.com/facebook/rocksdb/commit/92639b93a67c7ec28fd7d2de611eac759120ffce)
- tls: Fix race/unhandled case in reloadable_certificates [scylladb/seastar `9010bae849769b03e0edeaafd12fc5fec8dc46e7`](https://github.com/scylladb/seastar/commit/9010bae849769b03e0edeaafd12fc5fec8dc46e7)
- Simplify GenericRateLimiter algorithm (#8602) [facebook/rocksdb `82b81dc8b5e5370d1c77c860da9b518b5a7681ad`](https://github.com/facebook/rocksdb/commit/82b81dc8b5e5370d1c77c860da9b518b5a7681ad)
- epoll: fixes for races and early wakeups [nanomsg/nng `1514a532617b1fa7d4568a79a9d8ae24ceba1be9`](https://github.com/nanomsg/nng/commit/1514a532617b1fa7d4568a79a9d8ae24ceba1be9)
- Fix some shutdown races [grpc/grpc `b9eb180d4d5801c24d8578b8a0c85bfbe667c9bd`](https://github.com/grpc/grpc/commit/b9eb180d4d5801c24d8578b8a0c85bfbe667c9bd)

</details>

<details><summary>lock-order (18 examples)</summary>

- esp32c3: apply wifi deadlock fix from esp32s3 [apache/nuttx `93dbdd4a621e2ecb2fe69ca76f5460e1bf8c7780`](https://github.com/apache/nuttx/commit/93dbdd4a621e2ecb2fe69ca76f5460e1bf8c7780)
- Fix a bug where lock upgrade can incorrectly return deadlock status (#13575) [facebook/rocksdb `6c0e55a2a9e244ebbe71613c48eb3157ecfce9af`](https://github.com/facebook/rocksdb/commit/6c0e55a2a9e244ebbe71613c48eb3157ecfce9af)
- esp32c3-legacy: apply wifi deadlock fix from esp32s3 [apache/nuttx `847c1a615102a36df8a7b9b88138b947a441a1bc`](https://github.com/apache/nuttx/commit/847c1a615102a36df8a7b9b88138b947a441a1bc)
- BUG/MAJOR: lb/threads: fix AB/BA locking issue in round-robin LB [haproxy/haproxy `274ba6786236498de391f50675d3a2ec41a08638`](https://github.com/haproxy/haproxy/commit/274ba6786236498de391f50675d3a2ec41a08638)
- Fix a run initialization race condition. [jemalloc/jemalloc `e69bee01de62b56d3e585042d341743239568043`](https://github.com/jemalloc/jemalloc/commit/e69bee01de62b56d3e585042d341743239568043)
- Fix deadlock in the arenas.purge mallctl. [jemalloc/jemalloc `34457f51448e81f32a1bff16bbf600b79dd9ec5a`](https://github.com/jemalloc/jemalloc/commit/34457f51448e81f32a1bff16bbf600b79dd9ec5a)
- esp32s2: apply wifi deadlock fix from esp32s3 [apache/nuttx `b88aba5ddc355bd6504ad676f49bf8f26265d37c`](https://github.com/apache/nuttx/commit/b88aba5ddc355bd6504ad676f49bf8f26265d37c)
- darwin: avoid hotplug shutdown deadlock [libusb/libusb `94a5224ea1a7515c38c618694e8794e058c16412`](https://github.com/libusb/libusb/commit/94a5224ea1a7515c38c618694e8794e058c16412)
- esp32s3_wifi_adapter.c: Fix a deadlock [apache/nuttx `c0eaf1266158d473931ae3db5dfcda0bbaf493c2`](https://github.com/apache/nuttx/commit/c0eaf1266158d473931ae3db5dfcda0bbaf493c2)
- fixes #511 Want to be able to have deferred destroy of tasks and aios [nanomsg/nng `69190eb962f6a74be3d693f584320e42a79462d1`](https://github.com/nanomsg/nng/commit/69190eb962f6a74be3d693f584320e42a79462d1)
- esp32c6: apply wifi deadlock fix from esp32s3 [apache/nuttx `7a54488dbb1b63199ac24020487ffe84ba6541ea`](https://github.com/apache/nuttx/commit/7a54488dbb1b63199ac24020487ffe84ba6541ea)
- Fix bug in circular singleton creation detection [facebook/folly `be42394a1a5aae9689a7a02b7d9e9333829f37e6`](https://github.com/facebook/folly/commit/be42394a1a5aae9689a7a02b7d9e9333829f37e6)
- sys/suit: Introduce functions to provide a manifest in memory [RIOT-OS/RIOT `763474b48595c679919707e118e69c4fcf3bef30`](https://github.com/RIOT-OS/RIOT/commit/763474b48595c679919707e118e69c4fcf3bef30)
- esp32: apply wifi deadlock fix from esp32s3 [apache/nuttx `c954af0de181200b8d5de9e187963009cd2f946a`](https://github.com/apache/nuttx/commit/c954af0de181200b8d5de9e187963009cd2f946a)
- Fix race condition between log_.erase and log_.back [facebook/rocksdb `46fde6b65336c5e176d347b80422fd5f6a7ae7c2`](https://github.com/facebook/rocksdb/commit/46fde6b65336c5e176d347b80422fd5f6a7ae7c2)
- Fix TimedMutex deadlock when used both from fiber and main context [facebook/folly `2b06a7168bbcbb11384350d918767ab1804b9cdc`](https://github.com/facebook/folly/commit/2b06a7168bbcbb11384350d918767ab1804b9cdc)
- BUG/MEDIUM: listener/threads: fix an AB/BA locking issue in delete_listener() [haproxy/haproxy `6ee9f8df3bfbb811526cff3313da5758b1277bc6`](https://github.com/haproxy/haproxy/commit/6ee9f8df3bfbb811526cff3313da5758b1277bc6)
- net: if: fix lock inversion in address lifetime timeout [zephyrproject-rtos/zephyr `f693af0f5e5b3638737cab8e963629454d68a927`](https://github.com/zephyrproject-rtos/zephyr/commit/f693af0f5e5b3638737cab8e963629454d68a927)

</details>

<details><summary>move-work-out-of-lock (20 examples)</summary>

- Fix race in WriteBufferManager (#9009) [facebook/rocksdb `22d4dc5066fbfc1a9613c206ee9d8978929d7d5b`](https://github.com/facebook/rocksdb/commit/22d4dc5066fbfc1a9613c206ee9d8978929d7d5b)
- Make ring buffer thread-safe (#1213) [ros2/rclcpp `751727652d1620a04d8247a5a375b887fa80abe7`](https://github.com/ros2/rclcpp/commit/751727652d1620a04d8247a5a375b887fa80abe7)
- Fix two \`ErrorHandler\` race conditions (#11939) [facebook/rocksdb `4bd5aa4f5541d22ae52ff1ee2f6c9b782cf5ccdc`](https://github.com/facebook/rocksdb/commit/4bd5aa4f5541d22ae52ff1ee2f6c9b782cf5ccdc)
- Server-Client trimming form discovery info update (#1102) [eProsima/Fast-DDS `5063e70dd327aaf14794d3ab96c46cdb4524b942`](https://github.com/eProsima/Fast-DDS/commit/5063e70dd327aaf14794d3ab96c46cdb4524b942)
- BUG/MEDIUM: ssl: Fix unprotected 'ssl_sock_choose_sni_ctx' calls [haproxy/haproxy `e80bcb3eacbec961c90cd471fda9ce610d769a07`](https://github.com/haproxy/haproxy/commit/e80bcb3eacbec961c90cd471fda9ce610d769a07)
- net: tcp: Fix possible deadlock in tcp [zephyrproject-rtos/zephyr `9d801c4fdc79df587e22c7d3b45b3ce19cd4a5d1`](https://github.com/zephyrproject-rtos/zephyr/commit/9d801c4fdc79df587e22c7d3b45b3ce19cd4a5d1)
- Fix: compat_futex_noasync race condition [urcu/userspace-rcu `db21eff94739900b1ab51d231dfb281ead0a0fa5`](https://github.com/urcu/userspace-rcu/commit/db21eff94739900b1ab51d231dfb281ead0a0fa5)
- WaitSet deadlock fix (#2744) [eProsima/Fast-DDS `7b05712a5c5b3bdae2d189aa6f4e6662b2c63185`](https://github.com/eProsima/Fast-DDS/commit/7b05712a5c5b3bdae2d189aa6f4e6662b2c63185)
- drivers/sensors/gnss: Protect userlist with upper lock. [apache/nuttx `8331ae62a83235e2af8783d53f45622a6f3d4c4b`](https://github.com/apache/nuttx/commit/8331ae62a83235e2af8783d53f45622a6f3d4c4b)
- unix: protect fork in uv_spawn from signals [libuv/libuv `04289fa326b790c1a4abb236d1f9d913bacfc8c6`](https://github.com/libuv/libuv/commit/04289fa326b790c1a4abb236d1f9d913bacfc8c6)
- Fix context locking [openssl/openssl `770de3462c0d655a6543a6c1a2c0bda7b57178f9`](https://github.com/openssl/openssl/commit/770de3462c0d655a6543a6c1a2c0bda7b57178f9)
- Fix a race condition in the "arenas.extend" mallctl. [jemalloc/jemalloc `7b65180b32558fc4f2bc7b6ac5602f306ed3a014`](https://github.com/jemalloc/jemalloc/commit/7b65180b32558fc4f2bc7b6ac5602f306ed3a014)
- More win32 fixes + documentation. [grpc/grpc `8e1a55d4f9a45b68e610041d5b518bda3b138ce8`](https://github.com/grpc/grpc/commit/8e1a55d4f9a45b68e610041d5b518bda3b138ce8)
- Blob DB: Fix race condition between flush and write [facebook/rocksdb `5e9e5a4702d121e65c547b2e0ed1321e09462494`](https://github.com/facebook/rocksdb/commit/5e9e5a4702d121e65c547b2e0ed1321e09462494)
- kernel: fix race condition in sys_clock_announce() [zephyrproject-rtos/zephyr `3e2f30a7ef359424086dfff0664170afce303e2d`](https://github.com/zephyrproject-rtos/zephyr/commit/3e2f30a7ef359424086dfff0664170afce303e2d)
- \[PH2]\[Bug] Fixing possible deadlock [grpc/grpc `c4cd62a913078251fb45c006f7d126b7c68eb155`](https://github.com/grpc/grpc/commit/c4cd62a913078251fb45c006f7d126b7c68eb155)
- Flaky timer test fix (#2469) [ros2/rclcpp `f9c4894f96ea083fc5acfcea4f1ea83850759e63`](https://github.com/ros2/rclcpp/commit/f9c4894f96ea083fc5acfcea4f1ea83850759e63)
- Fix a deadlock while attempting to get the Primary EVP_RAND_CTX [openssl/openssl `01ea08049815325bf7719499f58c3799aa3fb555`](https://github.com/openssl/openssl/commit/01ea08049815325bf7719499f58c3799aa3fb555)
- Fix remove_session_cb called while holding ctx-&gt;lock [openssl/openssl `4be956b9cdeec99bd34f968ac4b595989d73abf7`](https://github.com/openssl/openssl/commit/4be956b9cdeec99bd34f968ac4b595989d73abf7)
- lib: posix: Fix mutex locking in pthread_cancel [zephyrproject-rtos/zephyr `4226c6d8b2c765848661bdb228befbcde4b1a215`](https://github.com/zephyrproject-rtos/zephyr/commit/4226c6d8b2c765848661bdb228befbcde4b1a215)

</details>

<details><summary>add-lock (20 examples)</summary>

- shell: telnet: Fix races when a client connection ends [zephyrproject-rtos/zephyr `adfe64d06c71d76c8983a02c2ea2b2b659d84425`](https://github.com/zephyrproject-rtos/zephyr/commit/adfe64d06c71d76c8983a02c2ea2b2b659d84425)
- iox-#33: fixing race condition while stopping timer thread [eclipse-iceoryx/iceoryx `a82b8914d8051eb0f158d9bb0020d673df5574c1`](https://github.com/eclipse-iceoryx/iceoryx/commit/a82b8914d8051eb0f158d9bb0020d673df5574c1)
- posix: cond: serialize lazy initialization of static condvars [zephyrproject-rtos/zephyr `22eb48bba57fcbd4e0211c7f74332fcb130397f9`](https://github.com/zephyrproject-rtos/zephyr/commit/22eb48bba57fcbd4e0211c7f74332fcb130397f9)
- Deflake ColumnFamilyTest.WriteStallSingleColumnFamily (#12294) [facebook/rocksdb `f046a8f6178a40d6c34a8277eaf9831ae88fea0b`](https://github.com/facebook/rocksdb/commit/f046a8f6178a40d6c34a8277eaf9831ae88fea0b)
- BUG/MEDIUM: connections: Hold the lock when wanting to kill a connection. [haproxy/haproxy `140237471e408736bb7162e68c572c710a66a526`](https://github.com/haproxy/haproxy/commit/140237471e408736bb7162e68c572c710a66a526)
- Fix get_typelookup_writer racing new_participant [eclipse-cyclonedds/cyclonedds `da72f23f41290a867858008bb51054c4c1f2a1c5`](https://github.com/eclipse-cyclonedds/cyclonedds/commit/da72f23f41290a867858008bb51054c4c1f2a1c5)
- Fix race in Notification Queue [facebook/folly `ed684e7693cf2ca054f19d9c2ab02e4e0acdf2b9`](https://github.com/facebook/folly/commit/ed684e7693cf2ca054f19d9c2ab02e4e0acdf2b9)
- Do not hold the base mutex while calling extent hooks. [jemalloc/jemalloc `9b1038d19c998b8c219eb08d083ca0328b7941f1`](https://github.com/jemalloc/jemalloc/commit/9b1038d19c998b8c219eb08d083ca0328b7941f1)
- fixed detection_based_tracker on visual studio 2013 and later [opencv/opencv `049a8949865f23cac30b086e129fd5559b846593`](https://github.com/opencv/opencv/commit/049a8949865f23cac30b086e129fd5559b846593)
- - Use cv::Mutex to safely update converged flag [opencv/opencv `180e54d09d13e90df722f5e0b821323d726f1380`](https://github.com/opencv/opencv/commit/180e54d09d13e90df722f5e0b821323d726f1380)
- \[xDS] Add mutex in streaming call promise wrapper (#43306) [grpc/grpc `44e46d5037e944b79db65d8bdd6b041639cf9e69`](https://github.com/grpc/grpc/commit/44e46d5037e944b79db65d8bdd6b041639cf9e69)
- drivers: pwm: pwm_mcux: make thread safe with mutex. [zephyrproject-rtos/zephyr `daaf06db94a4b9b64bb45ead01fc07ccccc84831`](https://github.com/zephyrproject-rtos/zephyr/commit/daaf06db94a4b9b64bb45ead01fc07ccccc84831)
- hotplug_exit: Mutex protection of context device list while cleaning it [libusb/libusb `6c0ae1ab456da49e7805115e77ce0428ace4ea41`](https://github.com/libusb/libusb/commit/6c0ae1ab456da49e7805115e77ce0428ace4ea41)
- Linux: Fix #81 URB double free race condition on device disconnect [libusb/libusb `737ba04ea40f19564b445fbb489907529e75edc9`](https://github.com/libusb/libusb/commit/737ba04ea40f19564b445fbb489907529e75edc9)
- close some idiotic race conditions [memcached/memcached `193a653e9678080f5ef7841ce93dca8e24116949`](https://github.com/memcached/memcached/commit/193a653e9678080f5ef7841ce93dca8e24116949)
- Avoid WBM pressure delay after fast rejection (#15343) [facebook/rocksdb `9b4c5422f062717380b4e2d30ed87daf4b220110`](https://github.com/facebook/rocksdb/commit/9b4c5422f062717380b4e2d30ed87daf4b220110)
- fix race crash for accepting new connections [memcached/memcached `ac939723874f1ebe1f0738af3855e81c026e9bc4`](https://github.com/memcached/memcached/commit/ac939723874f1ebe1f0738af3855e81c026e9bc4)
- input: fix touchevent race condition [apache/nuttx `9694760eb8cd40aaf4ccca860f699d731fe1ab8f`](https://github.com/apache/nuttx/commit/9694760eb8cd40aaf4ccca860f699d731fe1ab8f)
- gRPCLB and RR race fixes [grpc/grpc `90712d5e5dfc40ec694a031c70379cd3c9c94431`](https://github.com/grpc/grpc/commit/90712d5e5dfc40ec694a031c70379cd3c9c94431)
- evdns: fix race condition in evdns_getaddrinfo() [libevent/libevent `b59525ece4288d844fa31945eedddd859d58bfaa`](https://github.com/libevent/libevent/commit/b59525ece4288d844fa31945eedddd859d58bfaa)

</details>

<details><summary>remove-lock (20 examples)</summary>

- iox-#33: fixing race condition in stopTimerThread and improving code for windows impl [eclipse-iceoryx/iceoryx `46a79423417c92b52f9815127cbb4edbdf5d9b04`](https://github.com/eclipse-iceoryx/iceoryx/commit/46a79423417c92b52f9815127cbb4edbdf5d9b04)
- Fix bug affecting GetSortedWalFiles, Backups, Checkpoint (#9208) [facebook/rocksdb `2a67d475f1a3fe24b4baae6e590cecabca099464`](https://github.com/facebook/rocksdb/commit/2a67d475f1a3fe24b4baae6e590cecabca099464)
- Suggested fix for deadlock in waitForCompletion when closing bad client [eclipse-paho/paho.mqtt.c `503ae24d1f2176cdfdd27dc1f76eb307bebdb2ad`](https://github.com/eclipse-paho/paho.mqtt.c/commit/503ae24d1f2176cdfdd27dc1f76eb307bebdb2ad)
- Fix possible out-of-order/inconsistent seqno-to-time mapping (#13279) [facebook/rocksdb `b341dc8b05bd0e2499e22886733f25ad011d2a50`](https://github.com/facebook/rocksdb/commit/b341dc8b05bd0e2499e22886733f25ad011d2a50)
- darwin: remove workaround for data corruption bug [libuv/libuv `737f4f953fa908863c3492e6c6a1188acb58370c`](https://github.com/libuv/libuv/commit/737f4f953fa908863c3492e6c6a1188acb58370c)
- Fixed deadlock existing AsyncWriterThread. [eProsima/Fast-DDS `ae7584f770626ef9cd22769ebb898fc736f25aad`](https://github.com/eProsima/Fast-DDS/commit/ae7584f770626ef9cd22769ebb898fc736f25aad)
- drivers/sensors/sensor: always report POLLIN for fetch only sensor [apache/nuttx `4d3c5cac467232b985f48c29fab664f4f4543325`](https://github.com/apache/nuttx/commit/4d3c5cac467232b985f48c29fab664f4f4543325)
- Redo SyncPoints for flush while rolling test [facebook/rocksdb `b0469166564cb4a686ef33f8209513fdd8606be8`](https://github.com/facebook/rocksdb/commit/b0469166564cb4a686ef33f8209513fdd8606be8)
- BUG/MEDIUM: listener: use a self-locked list for the dequeue lists [haproxy/haproxy `01abd025084b4fe50e84189d1a83499cbf4825ed`](https://github.com/haproxy/haproxy/commit/01abd025084b4fe50e84189d1a83499cbf4825ed)
- Flat combining: Update statistics. [facebook/folly `b5737d0b620202f4c7d7d7bdb08cd79908892c51`](https://github.com/facebook/folly/commit/b5737d0b620202f4c7d7d7bdb08cd79908892c51)
- kernel/sched: Fix free-memory write when ISRs abort _current [zephyrproject-rtos/zephyr `f0fd54cb312d25201d9deb2ff34ebd69ffa9f4e1`](https://github.com/zephyrproject-rtos/zephyr/commit/f0fd54cb312d25201d9deb2ff34ebd69ffa9f4e1)
- BUG/MEDIUM: cli: make "show sess" really thread-safe [haproxy/haproxy `e6e52366c185db13ccaf0d2d669909c157d55923`](https://github.com/haproxy/haproxy/commit/e6e52366c185db13ccaf0d2d669909c157d55923)
- Server-Client trimming form discovery info update (#1102) [eProsima/Fast-DDS `5063e70dd327aaf14794d3ab96c46cdb4524b942`](https://github.com/eProsima/Fast-DDS/commit/5063e70dd327aaf14794d3ab96c46cdb4524b942)
- Eliminate the pipe mutex and use atomic for pipe closed. [nanomsg/nng `515cdff883f44fbd192f7d957f47d6e2e1385dd0`](https://github.com/nanomsg/nng/commit/515cdff883f44fbd192f7d957f47d6e2e1385dd0)
- kernel: work: fix race condition with cancel before work runs [zephyrproject-rtos/zephyr `656c09589ac48537fa71b4cdb4d6c8068cbdd4af`](https://github.com/zephyrproject-rtos/zephyr/commit/656c09589ac48537fa71b4cdb4d6c8068cbdd4af)
- drivers: timer: intel_adsp_timer: use sys_clock_lock() to fix SMP race [zephyrproject-rtos/zephyr `7735bf3bb8ddbcde032b52151dc9d12b0067867d`](https://github.com/zephyrproject-rtos/zephyr/commit/7735bf3bb8ddbcde032b52151dc9d12b0067867d)
- drivers: timer: hpet: use sys_clock_lock() to fix SMP race [zephyrproject-rtos/zephyr `59d4ffeea6aa51fe7541dc7dbad6bb98bdcde790`](https://github.com/zephyrproject-rtos/zephyr/commit/59d4ffeea6aa51fe7541dc7dbad6bb98bdcde790)
- drivers: ieee802154: rf2xx: Rem trx_state variable [zephyrproject-rtos/zephyr `2cfb11e0508c1e9efa6ef9c505fcfb5e48a27be5`](https://github.com/zephyrproject-rtos/zephyr/commit/2cfb11e0508c1e9efa6ef9c505fcfb5e48a27be5)
- MEDIUM: init/mworker: make the pipe register function a regular initcall [haproxy/haproxy `619a95f5ad090d2ed6195dd794b244ebe6a9317d`](https://github.com/haproxy/haproxy/commit/619a95f5ad090d2ed6195dd794b244ebe6a9317d)
- (wangle) express current Core functionality with a state machine [facebook/folly `1be516d1df75d5c33f9b064c288f1e8533f5c8c3`](https://github.com/facebook/folly/commit/1be516d1df75d5c33f9b064c288f1e8533f5c8c3)

</details>

<details><summary>use-trylock-or-timeout (20 examples)</summary>

- Fix Coverity Scan #1619415 [eclipse-mosquitto/mosquitto `422ea6ed26b184917c9034e10eccf8e7c77d1b50`](https://github.com/eclipse-mosquitto/mosquitto/commit/422ea6ed26b184917c9034e10eccf8e7c77d1b50)
- db_bench: fix hang on IO error (#5300) [facebook/rocksdb `92c60547fe1bc3254a18c2ff82e5398339cdb45b`](https://github.com/facebook/rocksdb/commit/92c60547fe1bc3254a18c2ff82e5398339cdb45b)
- sys: posix: pthread: fix mutex usage [RIOT-OS/RIOT `c0f39bb55f0160edb6d6add36fd9f49be2c3e746`](https://github.com/RIOT-OS/RIOT/commit/c0f39bb55f0160edb6d6add36fd9f49be2c3e746)
- bluetooth: host: smp: fix deadlock when public key generation fails [zephyrproject-rtos/zephyr `9757ffa5fa46612737bc4814d373443ba0d043a1`](https://github.com/zephyrproject-rtos/zephyr/commit/9757ffa5fa46612737bc4814d373443ba0d043a1)
- Fix TimedMutex deadlock when used both from fiber and main context [facebook/folly `2b06a7168bbcbb11384350d918767ab1804b9cdc`](https://github.com/facebook/folly/commit/2b06a7168bbcbb11384350d918767ab1804b9cdc)
- When calling ossl_crypto_condvar_wait_timeout() we must use real time [openssl/openssl `2b8d81534479b161dda063477272363fb2caef08`](https://github.com/openssl/openssl/commit/2b8d81534479b161dda063477272363fb2caef08)
- Stopped the SMP Linux port losing a mutex wake-up to a suspend signal (#753) [eclipse-threadx/threadx `47a5259002b0e51e7fbce1807f05a6987fe0ccd1`](https://github.com/eclipse-threadx/threadx/commit/47a5259002b0e51e7fbce1807f05a6987fe0ccd1)
- esp32: Update libc stubs to properly acquire/release locks. [apache/nuttx `d56e6de62832c7613d276155f08c8dc06e79d07e`](https://github.com/apache/nuttx/commit/d56e6de62832c7613d276155f08c8dc06e79d07e)
- net: sockets: Make sure that getaddrinfo() cannot hang forever [zephyrproject-rtos/zephyr `1897896e9739f93654430b172b7048134177a0a9`](https://github.com/zephyrproject-rtos/zephyr/commit/1897896e9739f93654430b172b7048134177a0a9)
- Simplify GenericRateLimiter algorithm (#8602) [facebook/rocksdb `82b81dc8b5e5370d1c77c860da9b518b5a7681ad`](https://github.com/facebook/rocksdb/commit/82b81dc8b5e5370d1c77c860da9b518b5a7681ad)
- Fixing mutex to not use unique_lock [facebook/rocksdb `a1d37602a0b9a31c0fc5a9869e57bd55884f6af9`](https://github.com/facebook/rocksdb/commit/a1d37602a0b9a31c0fc5a9869e57bd55884f6af9)
- drivers: eth_nxp_enet_qos: Don't block TX send [zephyrproject-rtos/zephyr `3db8bf768962763c2425f846fd0796f11061ea8d`](https://github.com/zephyrproject-rtos/zephyr/commit/3db8bf768962763c2425f846fd0796f11061ea8d)
- Bluetooth: ATT: Queue buffers on bt_att_send [zephyrproject-rtos/zephyr `ec89ae6ff41d8a4967c6e6cb17768872c748c3e9`](https://github.com/zephyrproject-rtos/zephyr/commit/ec89ae6ff41d8a4967c6e6cb17768872c748c3e9)
- drivers: flash: nrfx_qspi_nor: fix semaphore errors [zephyrproject-rtos/zephyr `3d8125a47c14ca060a3dbfee192181fc2dd0896e`](https://github.com/zephyrproject-rtos/zephyr/commit/3d8125a47c14ca060a3dbfee192181fc2dd0896e)
- Fix issues with v2/shared_mutex.hpp [boostorg/thread `610c3ae0717a2ffec34bec9e6a5717cb75ccec9e`](https://github.com/boostorg/thread/commit/610c3ae0717a2ffec34bec9e6a5717cb75ccec9e)
- add per node mutex for emulated futex [facebook/folly `8961aec70edc04d3e9f43fb28cc73d084896d8e1`](https://github.com/facebook/folly/commit/8961aec70edc04d3e9f43fb28cc73d084896d8e1)
- esp32s2: Update libc stubs to properly acquire/release locks. [apache/nuttx `075b0e5ac0bad0a93d316ea562abf09fd65a0041`](https://github.com/apache/nuttx/commit/075b0e5ac0bad0a93d316ea562abf09fd65a0041)
- Thread: update latch to use generation to prevent spurious wake-ups. [boostorg/thread `4cf80c6685cbaebf593df2ebb3f83bc2fecf54bc`](https://github.com/boostorg/thread/commit/4cf80c6685cbaebf593df2ebb3f83bc2fecf54bc)
- usb: fix possible deadlock in usb_transfer_sync() [zephyrproject-rtos/zephyr `cd7461495f1aeb4561d6a7e96c9f37b029805694`](https://github.com/zephyrproject-rtos/zephyr/commit/cd7461495f1aeb4561d6a7e96c9f37b029805694)
- fix(espidf): correct condvar clock mismatch in _z_condvar_wait_until (#1231) [eclipse-zenoh/zenoh-pico `c2088f198e5c697be1b51bee2916b97f3a9b919f`](https://github.com/eclipse-zenoh/zenoh-pico/commit/c2088f198e5c697be1b51bee2916b97f3a9b919f)

</details>

<details><summary>sem-to-mutex (6 examples)</summary>

- arch/sim: Use pthread_cond for signalling CPU initialisation done [apache/nuttx `5beb32bf0b1a9373f6a26a797e495757a2422e31`](https://github.com/apache/nuttx/commit/5beb32bf0b1a9373f6a26a797e495757a2422e31)
- bluetooth: host: smp: fix deadlock when public key generation fails [zephyrproject-rtos/zephyr `9757ffa5fa46612737bc4814d373443ba0d043a1`](https://github.com/zephyrproject-rtos/zephyr/commit/9757ffa5fa46612737bc4814d373443ba0d043a1)
- shell: use mutex for priority inheritance [zephyrproject-rtos/zephyr `aef316d17a5f8abdfeb359810ad23903ae7c135e`](https://github.com/zephyrproject-rtos/zephyr/commit/aef316d17a5f8abdfeb359810ad23903ae7c135e)
- net: ipv6: Improve Neighbor Discovery thread safety [zephyrproject-rtos/zephyr `7b6e7d6088905205d2bbd42aa37b6b02bd40eb7a`](https://github.com/zephyrproject-rtos/zephyr/commit/7b6e7d6088905205d2bbd42aa37b6b02bd40eb7a)
- drivers: i2c: npcx: use k_mutex for controller lock [zephyrproject-rtos/zephyr `e76a9c7d7dbc5c91495e8bfc2db5f205da8cd212`](https://github.com/zephyrproject-rtos/zephyr/commit/e76a9c7d7dbc5c91495e8bfc2db5f205da8cd212)
- drivers: i3c: i3c_mcux: a number of improvements and bug fixes [zephyrproject-rtos/zephyr `f55d281536e53b864d63bde9ab225b472b69add9`](https://github.com/zephyrproject-rtos/zephyr/commit/f55d281536e53b864d63bde9ab225b472b69add9)

</details>

<details><summary>priority-inheritance (1 examples)</summary>

- Correct the pthread mutex priority inheritance default setting [apache/nuttx `06d00b4c88764c8ee60e95f6e6cb44be0589e0d0`](https://github.com/apache/nuttx/commit/06d00b4c88764c8ee60e95f6e6cb44be0589e0d0)

</details>

<details><summary>signal-under-lock (3 examples)</summary>

- Refs #1538. Fixed use of condition variable [eProsima/Fast-DDS `e8e97cf299dee527788d3286f01e609497fe59ae`](https://github.com/eProsima/Fast-DDS/commit/e8e97cf299dee527788d3286f01e609497fe59ae)
- fixes #511 Want to be able to have deferred destroy of tasks and aios [nanomsg/nng `69190eb962f6a74be3d693f584320e42a79462d1`](https://github.com/nanomsg/nng/commit/69190eb962f6a74be3d693f584320e42a79462d1)
- Respect locking order in waitset attach/detach [eclipse-cyclonedds/cyclonedds `ed59c388f5b8b1deaba1fdb2d1ed7627c82e0c58`](https://github.com/eclipse-cyclonedds/cyclonedds/commit/ed59c388f5b8b1deaba1fdb2d1ed7627c82e0c58)

</details>

<details><summary>signal-outside-lock (4 examples)</summary>

- More reliable taskq fini; avoids deadlock during shutdown. [nanomsg/nng `6887900ae033add30ee0151b72abe927c5239588`](https://github.com/nanomsg/nng/commit/6887900ae033add30ee0151b72abe927c5239588)
- lib: posix: Fix mutex locking in pthread_cancel [zephyrproject-rtos/zephyr `4226c6d8b2c765848661bdb228befbcde4b1a215`](https://github.com/zephyrproject-rtos/zephyr/commit/4226c6d8b2c765848661bdb228befbcde4b1a215)
- Mark mutex as robust to prevent deadlocks (#1233) [FreeRTOS/FreeRTOS-Kernel `ad4e7238293cbe994e7450e1bc415136875da322`](https://github.com/FreeRTOS/FreeRTOS-Kernel/commit/ad4e7238293cbe994e7450e1bc415136875da322)
- Respect locking order in waitset attach/detach [eclipse-cyclonedds/cyclonedds `ed59c388f5b8b1deaba1fdb2d1ed7627c82e0c58`](https://github.com/eclipse-cyclonedds/cyclonedds/commit/ed59c388f5b8b1deaba1fdb2d1ed7627c82e0c58)

</details>

<details><summary>signal-to-broadcast (1 examples)</summary>

- urcu: fix compat_futex_noasync() [urcu/userspace-rcu `5b80127fe2aa3defd8a82acec727be2fc885087a`](https://github.com/urcu/userspace-rcu/commit/5b80127fe2aa3defd8a82acec727be2fc885087a)

</details>

<details><summary>atomic-or-volatile (20 examples)</summary>

- BUG/MEDIUM: peers: hold the refcnt until updating ts-&gt;seen [haproxy/haproxy `006a3acbde309f11190a003c4ac1c026480444e4`](https://github.com/haproxy/haproxy/commit/006a3acbde309f11190a003c4ac1c026480444e4)
- fix(ClientGoalHandle): Made mutex recursive to prevent deadlocks (#2267) [ros2/rclcpp `e103b8d37ed14216b495b75c72dda82cb7f98c6f`](https://github.com/ros2/rclcpp/commit/e103b8d37ed14216b495b75c72dda82cb7f98c6f)
- (wangle) fix a race condition in Core::maybeCallback [facebook/folly `c4035d0669465fa9e7ecb20f71633f71903fdeb7`](https://github.com/facebook/folly/commit/c4035d0669465fa9e7ecb20f71633f71903fdeb7)
- MEDIUM: threads: add thread_sync_release() to synchronize steps [haproxy/haproxy `9a1f57351d0d5a4ad4c28fed13848463bf0063c7`](https://github.com/haproxy/haproxy/commit/9a1f57351d0d5a4ad4c28fed13848463bf0063c7)
- Fix stop_ thread race [facebook/folly `a2206d8115d4ae508a45c5960425e858808ea869`](https://github.com/facebook/folly/commit/a2206d8115d4ae508a45c5960425e858808ea869)
- fix lost FlatCombining notifications [facebook/folly `6d16b1d46db39b8140b2e8d9788f38fcae2055ce`](https://github.com/facebook/folly/commit/6d16b1d46db39b8140b2e8d9788f38fcae2055ce)
- Fix data race [grpc/grpc `15626bb5274d4f0a65d9328af536b46f3a15e18b`](https://github.com/grpc/grpc/commit/15626bb5274d4f0a65d9328af536b46f3a15e18b)
- Recheck LockWAL() before WAL error recovery reserves the failed sequence (#15638) [facebook/rocksdb `dd7bd172c9a1905936c51e4ddc8739cc1615063f`](https://github.com/facebook/rocksdb/commit/dd7bd172c9a1905936c51e4ddc8739cc1615063f)
- Bluetooth: Controller: Fix auxiliary scan stop assertion check [zephyrproject-rtos/zephyr `1bbe209a30fcdab037c8ac9b96c33ea2249665e0`](https://github.com/zephyrproject-rtos/zephyr/commit/1bbe209a30fcdab037c8ac9b96c33ea2249665e0)
- fix lock order inversion in SharedPromise interrupt handler setting exn [facebook/folly `aa605f8e955876f4e99f0e769fa79fe49c76bf2f`](https://github.com/facebook/folly/commit/aa605f8e955876f4e99f0e769fa79fe49c76bf2f)
- Fix race in folly::coro::BoundedQueue [facebook/folly `e20b4e39a39d7c827f725b8007901a7ad78914b9`](https://github.com/facebook/folly/commit/e20b4e39a39d7c827f725b8007901a7ad78914b9)
- kernel: Make irq_{un}lock() APIs into a global spinlock in SMP mode [zephyrproject-rtos/zephyr `364cbae4128cbad61451446b8c724db210f0f109`](https://github.com/zephyrproject-rtos/zephyr/commit/364cbae4128cbad61451446b8c724db210f0f109)
- asm_volatile_pause: use isb on aarch64 (#1904) [facebook/folly `062c143072f25516e939762b549993f75dd9e767`](https://github.com/facebook/folly/commit/062c143072f25516e939762b549993f75dd9e767)
- Fix a flaky tsan test for DBTest2 (#7526) [facebook/rocksdb `f548a2a03cacdf1463bb4c63340569f846c73128`](https://github.com/facebook/rocksdb/commit/f548a2a03cacdf1463bb4c63340569f846c73128)
- BUG/MINOR: task: fix possibly missed event in inter-thread wakeups [haproxy/haproxy `13afcb7ab31a8f4e82ea943128706b5bd8df9e51`](https://github.com/haproxy/haproxy/commit/13afcb7ab31a8f4e82ea943128706b5bd8df9e51)
- Added test and fix for win32 condition_variable broadcast bug similar to #1803 [boostorg/thread `795cc23f3e5cf01d6edb3c14dda129552b61a929`](https://github.com/boostorg/thread/commit/795cc23f3e5cf01d6edb3c14dda129552b61a929)
- Fix persniketyness in tsan [openssl/openssl `8f9f0d2da0669a49fcb943eb433af1368461258a`](https://github.com/openssl/openssl/commit/8f9f0d2da0669a49fcb943eb433af1368461258a)
- Fix deadlock between (WriterThread/Compaction/IngestExternalFile) [facebook/rocksdb `9bd191d2f40bd775f010585025e47acde8e288c7`](https://github.com/facebook/rocksdb/commit/9bd191d2f40bd775f010585025e47acde8e288c7)
- Fix ThreadLocal races [facebook/folly `74502e3cc02daef719f6255cc55a7bebe0772a26`](https://github.com/facebook/folly/commit/74502e3cc02daef719f6255cc55a7bebe0772a26)
- drivers: adc: shell: fix periodic read not stopping on key press [zephyrproject-rtos/zephyr `660311db8402a79f39797eb6d102e28f1185a342`](https://github.com/zephyrproject-rtos/zephyr/commit/660311db8402a79f39797eb6d102e28f1185a342)

</details>

<details><summary>add-cancel-or-shutdown-path (20 examples)</summary>

- Fix: lttng perf counter deadlock [lttng/lttng-ust `20142124a2e34c287a277bbd7ef5b28697735d10`](https://github.com/lttng/lttng-ust/commit/20142124a2e34c287a277bbd7ef5b28697735d10)
- Fix two flaky unit tests in contrun clang_check (#15624) [facebook/rocksdb `ef2d052de6f2c649c627468e01d262a477ff27fa`](https://github.com/facebook/rocksdb/commit/ef2d052de6f2c649c627468e01d262a477ff27fa)
- kernel: thread timeout: Fix race condition [zephyrproject-rtos/zephyr `1b8c7a3038d98d8dd1aaf87ee5500ce88f66638b`](https://github.com/zephyrproject-rtos/zephyr/commit/1b8c7a3038d98d8dd1aaf87ee5500ce88f66638b)
- sched: pthread: Fix potential bugs in pthread_condclockwait.c [apache/nuttx `8ba67b7ec956065840b4490d9df0c557f0daa219`](https://github.com/apache/nuttx/commit/8ba67b7ec956065840b4490d9df0c557f0daa219)
- kernel: work: fix race condition with cancel before work runs [zephyrproject-rtos/zephyr `656c09589ac48537fa71b4cdb4d6c8068cbdd4af`](https://github.com/zephyrproject-rtos/zephyr/commit/656c09589ac48537fa71b4cdb4d6c8068cbdd4af)
- net: coap: fix socket closing in another thread [zephyrproject-rtos/zephyr `32f160cb55be1beb6f4eb62d95d971e4c29793d1`](https://github.com/zephyrproject-rtos/zephyr/commit/32f160cb55be1beb6f4eb62d95d971e4c29793d1)
- Fix race at server shutdown between actual shutdown and MatchOrQueue (#25541) [grpc/grpc `37bd0a0cbdda54c778cf39dc1290a63251aac764`](https://github.com/grpc/grpc/commit/37bd0a0cbdda54c778cf39dc1290a63251aac764)
- Deflake unit test \`DBErrorHandlingFSTest.AtomicFlushNoSpaceError\` (#13234) [facebook/rocksdb `cc30226b1fa63bc9e65a15c3dbef8e34784ee70c`](https://github.com/facebook/rocksdb/commit/cc30226b1fa63bc9e65a15c3dbef8e34784ee70c)
- net: tcp: Avoid partial ACK canceling retransmission timer [zephyrproject-rtos/zephyr `e14935ec6c6f13014868eb6d0e636c11c2f06268`](https://github.com/zephyrproject-rtos/zephyr/commit/e14935ec6c6f13014868eb6d0e636c11c2f06268)
- net: lib: coap: client: Do not hold lock in callback [zephyrproject-rtos/zephyr `9d1082464e3bd7893184c3c80b8c36efe218accc`](https://github.com/zephyrproject-rtos/zephyr/commit/9d1082464e3bd7893184c3c80b8c36efe218accc)
- Race condition fix attempt. [nanomsg/nng `4121745aad5b3a1c483c6bffb22dcae6e132d4f9`](https://github.com/nanomsg/nng/commit/4121745aad5b3a1c483c6bffb22dcae6e132d4f9)
- Set O_CLOEXEC by default when creating pipes to avoid race conditions resulting from concurrent Subprocess creations [facebook/folly `870912b89844e07283ff6d7e9602952f05ad3840`](https://github.com/facebook/folly/commit/870912b89844e07283ff6d7e9602952f05ad3840)
- \[RLS] release default child policy ref in WorkSerializer (#43773) [grpc/grpc `36a2ae2930d02c392e6e471c0d95d9d6e0c62dc9`](https://github.com/grpc/grpc/commit/36a2ae2930d02c392e6e471c0d95d9d6e0c62dc9)
- net: sockets: Fix recv() not being interrupted on close() [zephyrproject-rtos/zephyr `966eff642f407a3d1ba8208807f615dc502eece3`](https://github.com/zephyrproject-rtos/zephyr/commit/966eff642f407a3d1ba8208807f615dc502eece3)
- \[PH2] \[Bug] Fix server shutdown and start call race bug. [grpc/grpc `6edf5e0181004eea5b4141a7ca1dc90b59855eb1`](https://github.com/grpc/grpc/commit/6edf5e0181004eea5b4141a7ca1dc90b59855eb1)
- fixed detection_based_tracker on visual studio 2013 and later [opencv/opencv `049a8949865f23cac30b086e129fd5559b846593`](https://github.com/opencv/opencv/commit/049a8949865f23cac30b086e129fd5559b846593)
- Fix a TSAN reported race [grpc/grpc `43a2b176f1825151a379cb171896f134580ae4c4`](https://github.com/grpc/grpc/commit/43a2b176f1825151a379cb171896f134580ae4c4)
- fix race condition in grpc_tsi_alts_shutdown() [grpc/grpc `6d55db03bec2a08380482ea54244e0ba68aa137b`](https://github.com/grpc/grpc/commit/6d55db03bec2a08380482ea54244e0ba68aa137b)
- sensor: rts5912: fetch samples asyncronously [zephyrproject-rtos/zephyr `74d395ce1d7c5ae8e45d885ac364f5f78ed248f2`](https://github.com/zephyrproject-rtos/zephyr/commit/74d395ce1d7c5ae8e45d885ac364f5f78ed248f2)
- Recheck LockWAL() before WAL error recovery reserves the failed sequence (#15638) [facebook/rocksdb `dd7bd172c9a1905936c51e4ddc8739cc1615063f`](https://github.com/facebook/rocksdb/commit/dd7bd172c9a1905936c51e4ddc8739cc1615063f)

</details>

<details><summary>async-signal-safety (0 examples)</summary>

No matches.

</details>

<details><summary>complete-unlock-on-exit (20 examples)</summary>

- Refs #1469. Fixed deadlock. [eProsima/Fast-DDS `b27c3dbe53b8fcc9ffb7e14597eb73d1cc8e01d0`](https://github.com/eProsima/Fast-DDS/commit/b27c3dbe53b8fcc9ffb7e14597eb73d1cc8e01d0)
- Fix possible deadlock in GILAwareManualExecutor [facebook/folly `6616c8e8d5f29aa173f464c956b5bc3542f840e4`](https://github.com/facebook/folly/commit/6616c8e8d5f29aa173f464c956b5bc3542f840e4)
- video/v4l2: fix capture lifecycle race conditions [apache/nuttx `e2d85bf59e6c8577adaf3c16aeb818ed1ab52704`](https://github.com/apache/nuttx/commit/e2d85bf59e6c8577adaf3c16aeb818ed1ab52704)
- websocket transport: use inline SP objects [nanomsg/nng `a43eb958e47f4c70725299845a3b7c69bbba9467`](https://github.com/nanomsg/nng/commit/a43eb958e47f4c70725299845a3b7c69bbba9467)
- Add a missing mutex unlock in malloc_init_hard() error path. [jemalloc/jemalloc `1d1cee127aebc6ca25207435ddc6ae5d9bb90d41`](https://github.com/jemalloc/jemalloc/commit/1d1cee127aebc6ca25207435ddc6ae5d9bb90d41)
- BUG/MEDIUM: queues: Stricly respect maxconn for outgoing connections [haproxy/haproxy `3372a2ea000dbfa29a1fcb5643e7e259603ec331`](https://github.com/haproxy/haproxy/commit/3372a2ea000dbfa29a1fcb5643e7e259603ec331)
- drivers/sensors: Do not hold the upper lock across lower open/close. [apache/nuttx `49d2559d550525fd7288d874fdfb2cb5fdeb5a9f`](https://github.com/apache/nuttx/commit/49d2559d550525fd7288d874fdfb2cb5fdeb5a9f)
- fixes #511 Want to be able to have deferred destroy of tasks and aios [nanomsg/nng `69190eb962f6a74be3d693f584320e42a79462d1`](https://github.com/nanomsg/nng/commit/69190eb962f6a74be3d693f584320e42a79462d1)
- pkg/xipfs/fs: fix double mutex lock in unlink handler [RIOT-OS/RIOT `f61108e17935945d140e04009cfea08a0f6d3581`](https://github.com/RIOT-OS/RIOT/commit/f61108e17935945d140e04009cfea08a0f6d3581)
- fix(eventloop): release timer mutex while executing callbacks [open62541/open62541 `a29a5ba2d9b13a79056d797e127816037c28f8dc`](https://github.com/open62541/open62541/commit/a29a5ba2d9b13a79056d797e127816037c28f8dc)
- lib: posix: mutex: to_posix_mutex should be spinlocked [zephyrproject-rtos/zephyr `d489ec087ed5a0b4a8c104e2f5fb9a302419d96b`](https://github.com/zephyrproject-rtos/zephyr/commit/d489ec087ed5a0b4a8c104e2f5fb9a302419d96b)
- gnrc: fix possibly ommited mutex unlock in ng_ipv6_netif_init_by_dev [RIOT-OS/RIOT `3efd2e9fae14786deefbd410012dc0f8b034f578`](https://github.com/RIOT-OS/RIOT/commit/3efd2e9fae14786deefbd410012dc0f8b034f578)
- Properly pair entity_pin/mutex_lock [eclipse-cyclonedds/cyclonedds `bf25c6ec807c1b33b23e5369d3715cce8b2fc7f0`](https://github.com/eclipse-cyclonedds/cyclonedds/commit/bf25c6ec807c1b33b23e5369d3715cce8b2fc7f0)
- tiva/sock_can: correct mutex lock cycle [apache/nuttx `e560111dbb98e0500b8f6bd021377cc95b4eeaee`](https://github.com/apache/nuttx/commit/e560111dbb98e0500b8f6bd021377cc95b4eeaee)
- Fix deadlock with security and timers. \[11923] (#2034) [eProsima/Fast-DDS `c0783e7217e05cd27dd732da0427b87798e382b5`](https://github.com/eProsima/Fast-DDS/commit/c0783e7217e05cd27dd732da0427b87798e382b5)
- Bluetooth: Host: Run tx processor on its own thread [zephyrproject-rtos/zephyr `f101976e31fdaa461ed2f2494f3bc9cef84c9cff`](https://github.com/zephyrproject-rtos/zephyr/commit/f101976e31fdaa461ed2f2494f3bc9cef84c9cff)
- ITE: drivers/i2c: Fix mutex bug [zephyrproject-rtos/zephyr `cffcc1901e032a1e1660e8d657b6362a60f84c23`](https://github.com/zephyrproject-rtos/zephyr/commit/cffcc1901e032a1e1660e8d657b6362a60f84c23)
- posix: Avoid use of internal mutex methods [RTEMS/rtems `dbd65507a2fa452a1df3718d3b467dc8a6171358`](https://github.com/RTEMS/rtems/commit/dbd65507a2fa452a1df3718d3b467dc8a6171358)
- BUG/MEDIUM: mux-h1: Fix a deadlock when a 408 error is pending for a client [haproxy/haproxy `cc043f66b7d6479866037bae00e27fd34fbee70b`](https://github.com/haproxy/haproxy/commit/cc043f66b7d6479866037bae00e27fd34fbee70b)
- net: lib: lwm2m: Fix missing mutex unlock [zephyrproject-rtos/zephyr `30b30c29a32da98beadb08ec3a92f65abe138e18`](https://github.com/zephyrproject-rtos/zephyr/commit/30b30c29a32da98beadb08ec3a92f65abe138e18)

</details>

<details><summary>mask-interrupts-around-state (20 examples)</summary>

- debug: SystemView fix [zephyrproject-rtos/zephyr `a304528f51fccdc674d1db4c9d396423d2edbf52`](https://github.com/zephyrproject-rtos/zephyr/commit/a304528f51fccdc674d1db4c9d396423d2edbf52)
- boards: cxd56xx: Add wifi_smp configuration [apache/nuttx `5feab8057cb9d639c2e7967e0de93d4b8fa65295`](https://github.com/apache/nuttx/commit/5feab8057cb9d639c2e7967e0de93d4b8fa65295)
- drivers: serial: nrfx_uarte: Add lock to uart_rx_disable [zephyrproject-rtos/zephyr `317de0c6dea11466f7465addeeb7d04076f32f4f`](https://github.com/zephyrproject-rtos/zephyr/commit/317de0c6dea11466f7465addeeb7d04076f32f4f)
- kernel: fix race condition when spawning a thread with a delay [zephyrproject-rtos/zephyr `f421ec23ada99f2fd0c3d77e23e4faa01155e2fd`](https://github.com/zephyrproject-rtos/zephyr/commit/f421ec23ada99f2fd0c3d77e23e4faa01155e2fd)
- drivers: espi: rts5912: make send_oob an atomic operation [zephyrproject-rtos/zephyr `835f35d033eba14ea1c0dd6f37e646380100fe31`](https://github.com/zephyrproject-rtos/zephyr/commit/835f35d033eba14ea1c0dd6f37e646380100fe31)
- arm64/zynq-mpsoc: fix race condition in txint handler [apache/nuttx `382d38b4e05e36c672fcccc09dfcbb620ad59ed7`](https://github.com/apache/nuttx/commit/382d38b4e05e36c672fcccc09dfcbb620ad59ed7)
- Fix some timer race conditions [apache/nuttx `81ca27c9b07ba29e06ac22482d9a4994e5bdf0cb`](https://github.com/apache/nuttx/commit/81ca27c9b07ba29e06ac22482d9a4994e5bdf0cb)
- arch/espressif: serialize Wi-Fi RX queue access. [apache/nuttx `54ee939f826730d266a0e23c968f5f670d92364d`](https://github.com/apache/nuttx/commit/54ee939f826730d266a0e23c968f5f670d92364d)
- Bluetooth: Fix race condition when initializing ECC FIFO [zephyrproject-rtos/zephyr `71680a60530e78592e09d90e6e1b0eb8ffc0f9ea`](https://github.com/zephyrproject-rtos/zephyr/commit/71680a60530e78592e09d90e6e1b0eb8ffc0f9ea)
- Revert "sched: Remove a redundant critical section" [apache/nuttx `102a6357ca31898207767d917bff4b7346e570da`](https://github.com/apache/nuttx/commit/102a6357ca31898207767d917bff4b7346e570da)
- soc: rtl87x2g: fix ROM ISR restore for direct ISRs and add irq_lock [zephyrproject-rtos/zephyr `a557d2ccb814ab5ea6c3dc4a1f9342c481b59cfe`](https://github.com/zephyrproject-rtos/zephyr/commit/a557d2ccb814ab5ea6c3dc4a1f9342c481b59cfe)
- drivers/pipes: change rmutex to rspinlock [apache/nuttx `56890907c7e462610ef3c1ddcace85e56aa76e93`](https://github.com/apache/nuttx/commit/56890907c7e462610ef3c1ddcace85e56aa76e93)
- ITE: drivers/gpio: Add critical section to avoid race condition [zephyrproject-rtos/zephyr `7a2e86f56313a3570c739038efbc30075d2748d8`](https://github.com/zephyrproject-rtos/zephyr/commit/7a2e86f56313a3570c739038efbc30075d2748d8)
- drivers: clock_control: nrf: Add protection to getting item from list [zephyrproject-rtos/zephyr `a124f2903286142562ef58613c869c9bf4925cc3`](https://github.com/zephyrproject-rtos/zephyr/commit/a124f2903286142562ef58613c869c9bf4925cc3)
- arch/arm: Add gic lock for GICD_ICFGR RMW operations. [apache/nuttx `8e68c7a8107fcdafb329b8d2a760996e52e09777`](https://github.com/apache/nuttx/commit/8e68c7a8107fcdafb329b8d2a760996e52e09777)
- sensor: rts5912: fetch samples asyncronously [zephyrproject-rtos/zephyr `74d395ce1d7c5ae8e45d885ac364f5f78ed248f2`](https://github.com/zephyrproject-rtos/zephyr/commit/74d395ce1d7c5ae8e45d885ac364f5f78ed248f2)
- x86: Lock interrupts when connecting interrupts [zephyrproject-rtos/zephyr `616ca2159937cbf98801408a80c0c209818d1fc2`](https://github.com/zephyrproject-rtos/zephyr/commit/616ca2159937cbf98801408a80c0c209818d1fc2)
- drivers/virtio-gpu: Avoid calling free in IRQ [apache/nuttx `f4bfde4d475df0b16c8519aebce818cc663a7108`](https://github.com/apache/nuttx/commit/f4bfde4d475df0b16c8519aebce818cc663a7108)
- arch/x86: Make irq_offload SMP-safe on x86_64 [zephyrproject-rtos/zephyr `7f0b5edd8c23ce1b285d00f7f376e5ad5a23c6ef`](https://github.com/zephyrproject-rtos/zephyr/commit/7f0b5edd8c23ce1b285d00f7f376e5ad5a23c6ef)
- arch: xtensa: Fix arch_is_in_isr() race condition [zephyrproject-rtos/zephyr `85b8ae9b6ac421159f9f6726b73bd1d696fb45b8`](https://github.com/zephyrproject-rtos/zephyr/commit/85b8ae9b6ac421159f9f6726b73bd1d696fb45b8)

</details>

<details><summary>change-lock-target (20 examples)</summary>

- Make CacheWithSecondaryAdapter reservation accounting more robust (#12059) [facebook/rocksdb `2222caec9e0648f97b50bbcfffbd94c4f38e43b9`](https://github.com/facebook/rocksdb/commit/2222caec9e0648f97b50bbcfffbd94c4f38e43b9)
- Add thread annotations to tls files and fix ASAN race in SetWatchStatusCallback (#26925) [grpc/grpc `f204224206d4ea6f3c01597698a7e6fa5df9b450`](https://github.com/grpc/grpc/commit/f204224206d4ea6f3c01597698a7e6fa5df9b450)
- Make em destroy underlying descriptor objects (and their corresponding libevent [grpc/grpc `5ef51949bcd339c8bc615ec98f13c71bc503484a`](https://github.com/grpc/grpc/commit/5ef51949bcd339c8bc615ec98f13c71bc503484a)
- \[tsan] Race fix in chaotic good client transport (#37658) [grpc/grpc `1769b20533a6098279ce7f69fa6f9c4dea1d53a4`](https://github.com/grpc/grpc/commit/1769b20533a6098279ce7f69fa6f9c4dea1d53a4)
- Updates to fix interruption-point inconsistencies. [boostorg/thread `aebbcda3fef1363e17b262fcd3b8e56ebb601f63`](https://github.com/boostorg/thread/commit/aebbcda3fef1363e17b262fcd3b8e56ebb601f63)
- Fix: deadlock when thread join is issued in read-side C.S. [urcu/userspace-rcu `731ccb963c80afd067e20acee2f9bd7cb4875ffb`](https://github.com/urcu/userspace-rcu/commit/731ccb963c80afd067e20acee2f9bd7cb4875ffb)
- Fixed error in previous commit for getting mutex in MesageReceiver [eProsima/Fast-DDS `9e116843ea305194f396986766fb690504c4aee3`](https://github.com/eProsima/Fast-DDS/commit/9e116843ea305194f396986766fb690504c4aee3)
- driver/sensor: slove deadlock issue because ept/devlist using same lock [apache/nuttx `48b46673186b2c1261182dbe52786d617be68e43`](https://github.com/apache/nuttx/commit/48b46673186b2c1261182dbe52786d617be68e43)
- Fixed a dependency issue of ThreadLocalPtr [facebook/rocksdb `908100399cdc8855980ca9f8c05d37836857ab79`](https://github.com/facebook/rocksdb/commit/908100399cdc8855980ca9f8c05d37836857ab79)
- Condition variable fix [eProsima/Fast-DDS `700b97a3b871612e4452ff81a608a3f632f42611`](https://github.com/eProsima/Fast-DDS/commit/700b97a3b871612e4452ff81a608a3f632f42611)
- Avoid referencing dds_global in dds_whc [eclipse-cyclonedds/cyclonedds `1a07c937ddc31fdfc2e3d283d4ac00436a1289c9`](https://github.com/eclipse-cyclonedds/cyclonedds/commit/1a07c937ddc31fdfc2e3d283d4ac00436a1289c9)
- darwin: add missing locking around cached device list cleanup [libusb/libusb `4e2de881cf0f8b38b1e19c078d19b4628f38c732`](https://github.com/libusb/libusb/commit/4e2de881cf0f8b38b1e19c078d19b4628f38c732)
- net: sockets: tls: Optimze helper buffer for sendmsg and CID check [zephyrproject-rtos/zephyr `ba047342201ea1373534b77154b8ff47d5bb5779`](https://github.com/zephyrproject-rtos/zephyr/commit/ba047342201ea1373534b77154b8ff47d5bb5779)
- core: fix parallel_for data race [opencv/opencv `491502a349010498571397217e3f7c1f7dbadda1`](https://github.com/opencv/opencv/commit/491502a349010498571397217e3f7c1f7dbadda1)
- Ensure the destruction order of PosixEnv and ThreadLocalPtr [facebook/rocksdb `00d6edf6a0080ac3961e56213ae962ec1d570daa`](https://github.com/facebook/rocksdb/commit/00d6edf6a0080ac3961e56213ae962ec1d570daa)
- Fix ConstructorCallback destructor consistency issue [facebook/folly `cf3af766b40afec7a3462d95c4e179a7bd8f481b`](https://github.com/facebook/folly/commit/cf3af766b40afec7a3462d95c4e179a7bd8f481b)
- Fix ddsperf race conditions [eclipse-cyclonedds/cyclonedds `6ad99463ce87e6d9cbf92c5ae789e67379da6980`](https://github.com/eclipse-cyclonedds/cyclonedds/commit/6ad99463ce87e6d9cbf92c5ae789e67379da6980)
- fixes #711 mutex / condition var triggering assertion on Windows [nanomsg/nanomsg `bdae89d28d16d29bbeda2abf0152936afa4db03a`](https://github.com/nanomsg/nanomsg/commit/bdae89d28d16d29bbeda2abf0152936afa4db03a)
- Fixed error in previous commit for getting mutex in MesageReceiver [eProsima/Fast-DDS `923d81f52815a802632e6bf8f03ca50f779804e9`](https://github.com/eProsima/Fast-DDS/commit/923d81f52815a802632e6bf8f03ca50f779804e9)
- drivers/sensors/gnss: using new buffer lock avoid deadlock [apache/nuttx `9599302f10c7d982fc452e3d61559f3618b9e50b`](https://github.com/apache/nuttx/commit/9599302f10c7d982fc452e3d61559f3618b9e50b)

</details>

<details><summary>retain-object-until-work-finishes (2 examples)</summary>

- tls: Fix race/unhandled case in reloadable_certificates [scylladb/seastar `9010bae849769b03e0edeaafd12fc5fec8dc46e7`](https://github.com/scylladb/seastar/commit/9010bae849769b03e0edeaafd12fc5fec8dc46e7)
- Fix DBImpl::NotifyOnCompactionCompleted data race [facebook/rocksdb `6b3c71f6ed40236b33d1fc3cf3db7b99a29f87eb`](https://github.com/facebook/rocksdb/commit/6b3c71f6ed40236b33d1fc3cf3db7b99a29f87eb)

</details>

<details><summary>serialize-work-on-owner-queue (5 examples)</summary>

- mgmt: mcumgr: Use dedicated work queue for SMP [zephyrproject-rtos/zephyr `698c4b024367076843e9bfbc2db0182680eb6fde`](https://github.com/zephyrproject-rtos/zephyr/commit/698c4b024367076843e9bfbc2db0182680eb6fde)
- drivers: usb_dc_nrfx: Use dedicated work queue for handling ISR events [zephyrproject-rtos/zephyr `f69e194ece46e17f01923ce2963ce4d63c14c927`](https://github.com/zephyrproject-rtos/zephyr/commit/f69e194ece46e17f01923ce2963ce4d63c14c927)
- ipc: ipc_service: icbmsg backend: workaround endpoint binding deadlock [zephyrproject-rtos/zephyr `1e6e6a228ff0ca635bf64067aab9001f4a3147c7`](https://github.com/zephyrproject-rtos/zephyr/commit/1e6e6a228ff0ca635bf64067aab9001f4a3147c7)
- ipc: icmsg: Dedicated workqueue for ICMSG backend [zephyrproject-rtos/zephyr `5b12b6ab554c0ef10f62b822a05e5823d73dd318`](https://github.com/zephyrproject-rtos/zephyr/commit/5b12b6ab554c0ef10f62b822a05e5823d73dd318)
- mgmt: smp: Fix race condition by using same work queue [zephyrproject-rtos/zephyr `9fa82f0d8d29d1f808829e16c09bb3942f53aa3b`](https://github.com/zephyrproject-rtos/zephyr/commit/9fa82f0d8d29d1f808829e16c09bb3942f53aa3b)

</details>

<details><summary>other (20 examples)</summary>

- USB HUB: Fix a deadlock that can occur if the HCD and the HUB try to share the high priority work queue.  Now how work must be done on the low priority work queue. [apache/nuttx `6d66546c313ab308c17e9d00fc7ed3fa9daa72a9`](https://github.com/apache/nuttx/commit/6d66546c313ab308c17e9d00fc7ed3fa9daa72a9)
- drivers: gpio: tca6424a: fix race condition in port_get_raw() [zephyrproject-rtos/zephyr `028abf54ba95f1eebe39ee4842455253325b401f`](https://github.com/zephyrproject-rtos/zephyr/commit/028abf54ba95f1eebe39ee4842455253325b401f)
- Fix WAL corruption from checkpoint/backup race condition [facebook/rocksdb `0cdaa1a804d69f24a8193bc48117af5cce3eb576`](https://github.com/facebook/rocksdb/commit/0cdaa1a804d69f24a8193bc48117af5cce3eb576)
- smp: allow more than 128 in-flight operations on core-to-core queue [scylladb/seastar `15a92cfe7aa43748c9afb88878bbe7eeac5e229c`](https://github.com/scylladb/seastar/commit/15a92cfe7aa43748c9afb88878bbe7eeac5e229c)
- net: tcp: Avoid deadlock in updating the TCP receive window [zephyrproject-rtos/zephyr `d74bd3d7d1a77c1324335a030bf81d1ac310ffcf`](https://github.com/zephyrproject-rtos/zephyr/commit/d74bd3d7d1a77c1324335a030bf81d1ac310ffcf)
- threads.h: Support mtx_timedlock and recursive mutex [apache/nuttx `4f0957aca0a44253b1fa66dc03ca87d2506b4807`](https://github.com/apache/nuttx/commit/4f0957aca0a44253b1fa66dc03ca87d2506b4807)
- fix potential race condition with setting the alignment flag and changing the threadid of a page [microsoft/mimalloc `5f82b5c9cbb2531bf265453f0876a3f78ce387c8`](https://github.com/microsoft/mimalloc/commit/5f82b5c9cbb2531bf265453f0876a3f78ce387c8)
- major bug and a dead lock fixed [redis/redis `a440ecf0d36d22305f994a4482e60099720c47f3`](https://github.com/redis/redis/commit/a440ecf0d36d22305f994a4482e60099720c47f3)
- use relaxed_atomic in CacheLocality [facebook/folly `6eb46044d6d44741178dd632317ff9d28f5ce235`](https://github.com/facebook/folly/commit/6eb46044d6d44741178dd632317ff9d28f5ce235)
- debug: coredump: Avoid taking mutex in isr with in memory coredump backend [zephyrproject-rtos/zephyr `4cb58ab3a8de78c85e7afbaccb70c7168be78945`](https://github.com/zephyrproject-rtos/zephyr/commit/4cb58ab3a8de78c85e7afbaccb70c7168be78945)
- Fixed a rare deadlock in DBTest.ThreadStatusFlush [facebook/rocksdb `a203b913c1851897e9ebf0f669d5f56e422dac8a`](https://github.com/facebook/rocksdb/commit/a203b913c1851897e9ebf0f669d5f56e422dac8a)
- BUG/MEDIUM: debug/lua: Use internal hlua function to dump the lua traceback [haproxy/haproxy `cc2c4f8f4c1d8613b481d1b346e083a9d2462811`](https://github.com/haproxy/haproxy/commit/cc2c4f8f4c1d8613b481d1b346e083a9d2462811)
- Must hold mutex on the destination during backups.  Add documentation to [sqlite/sqlite `662c58c9ba7fbcfd84ad4c25339d52d94ccab417`](https://github.com/sqlite/sqlite/commit/662c58c9ba7fbcfd84ad4c25339d52d94ccab417)
- Fix race in network status monitor [grpc/grpc `ce14c30460394336c42b8304ad2fd3e0d775d61f`](https://github.com/grpc/grpc/commit/ce14c30460394336c42b8304ad2fd3e0d775d61f)
- gnrc_ipv6_nib: fix acquire race on gnrc_ipv6_nib_get_next_hop_l2addr() [RIOT-OS/RIOT `4b4eaf3b76e73c17761ce12fb99dd6ceb635bd8d`](https://github.com/RIOT-OS/RIOT/commit/4b4eaf3b76e73c17761ce12fb99dd6ceb635bd8d)
- libnetworking: Avoid deadlock during starvation [RTEMS/rtems `b3cee28a519e96082d4309447d268dd4740a187c`](https://github.com/RTEMS/rtems/commit/b3cee28a519e96082d4309447d268dd4740a187c)
- macos: fix fsevents thread race conditions (#3909) [libuv/libuv `e613fdd83cb1fb448ac0ebace7ade055d0068829`](https://github.com/libuv/libuv/commit/e613fdd83cb1fb448ac0ebace7ade055d0068829)
- wifi: eswifi: fix random crash due to work-&gt;handler set to NULL [zephyrproject-rtos/zephyr `f93c68239e2c08503676e9b8cdff8e2599ef9b8d`](https://github.com/zephyrproject-rtos/zephyr/commit/f93c68239e2c08503676e9b8cdff8e2599ef9b8d)
- Fix race in call.c [grpc/grpc `04c447977eef65fcd935b9d0326f14898b054692`](https://github.com/grpc/grpc/commit/04c447977eef65fcd935b9d0326f14898b054692)
- mgmt: mcumgr: transport: smp_bt: Fix bridge deadlock on disconnect [zephyrproject-rtos/zephyr `3786bc55ad18347917a2c38b0d657c93f8ec52f1`](https://github.com/zephyrproject-rtos/zephyr/commit/3786bc55ad18347917a2c38b0d657c93f8ec52f1)

</details>
