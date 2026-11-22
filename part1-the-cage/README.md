# Part 1: The Cage — Sandbox Confinement, Storage & Syscall Mediation

## Overview
Part 1 documents the low-level confinement, virtualization platform engine, system call trap behavior, and storage durability semantics of Google's Gemini Notebook execution container.

## 1. Virtualization Substrate: gVisor Sentry (Consistent with `systrap`, Tier 2)
* **Application Kernel**: Google gVisor / Sentry (emulating Linux 4.19 ABI).
* **Platform Engine**: Behavioral indicators are **consistent with `systrap` (Tier 2 inference)**:
  * CPUID Leaf `0x40000000` returns `eax=0` with zeroed vendor bytes (`\x00`). *Note: Because Sentry synthesizes CPUID responses, this confirms hypervisor signature masking rather than directly proving the backend.*
  * Syscall overhead (`SYS_getpid`) measures **~1,205.88 ns (1.2 µs)**, matching the user-space context switch round-trip through host `seccomp-bpf` and Sentry goroutine scheduler. *Note: Trap latency alone does not definitively prove the engine.*
  * `PTRACE_SYSEMU` is implemented and returns success (`ret=0`) on a traced child (tested via `scripts/probe_systrap_kvm.py`).
  * Direct execution of strict seccomp transitions returns `EINVAL (errno=22)` as Sentry recognizes but stubs nested seccomp modes (tested via `scripts/probe_systrap_kvm.py`).

## 2. Storage Subsystem: Ephemeral Overlay + Plan 9 Gofer (FD 9)
* **Rootfs (`/`)**: Ephemeral `overlayfs` mounted with standard read/write permissions for `uid=1000(sandbox)`. All root-level writes are discarded upon session teardown.
* **Workspace (`/workspace`)**: Backed by a host Plan 9 (9P) Gofer mount connected over file descriptor 9 (`mountinfo: 9p ... fd=9`).
* **Cache Coherency & mmap**: Writes to `MAP_SHARED` memory regions are immediately visible to separate file descriptor reads (`cache_coherent: true`), with `msync(MS_SYNC)` completing in **56.3 µs** (tested via `scripts/probe_mmap_msync.py`).
* **Hermetic Traversal Protection**: Symlinks created within 9P referencing `/etc/passwd` or `../../` resolve strictly within Sentry's virtual VFS, preventing host filesystem escapes (tested via `scripts/probe_symlink_traversal.py`). Cross-device hardlinks fail with `EXDEV (errno=18)`.

## 3. Network Isolation
* Strict air-gap: `lo` (127.0.0.1) and `eth0` (192.168.1.1) exist, but the routing table contains zero default routes. Direct connection attempts to external IPs or metadata services (`169.254.169.254`) fail immediately with `ENETUNREACH (Errno 101)`.

## Evidence & Reproduction Scripts
* `evidence/proc_cpuinfo.txt`: CPU core definitions and feature flags.
* `evidence/proc_meminfo.txt`: Dynamic memory accounting (MemTotal: 8,388,608 kB = 8 GiB).
* `evidence/proc_mounts.txt`: Full mount table showing overlayfs and 9P mounts.
* `evidence/proc_net_route.txt`: Zero-route network namespace routing table.
* `evidence/proc_net_tcp.txt`: Ingress socket table.
* `scripts/probe_systrap_kvm.py`: Syscall timing calibration benchmark, raw CPUID leaf 0x40000000 execution, PTRACE_SYSEMU test, and SYS_seccomp rejection probe.
* `scripts/probe_ptrace_scope.py`: Full Yama relational ptrace validation (PID 1 ATTACH/SEIZE rejection, child TRACEME, and parent-to-child attachment).
* `scripts/probe_9p_fs.py`: Synchronous fsync IOPS benchmark.
* `scripts/probe_mmap_msync.py`: 9P mmap MAP_SHARED msync latency and page cache coherency benchmark.
* `scripts/probe_symlink_traversal.py`: Symlink escape testing (/etc/passwd, ../../) and cross-device hardlink rejection.
