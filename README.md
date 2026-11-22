# Gemini Notebook Systems Architecture: Empirical Sandbox Dissection

> Google engineered the agent workbench. We audited the syscalls, orchestrator binaries, and virtualization cage.

Independent black-box verification and empirical systems measurements of Google's **Gemini Notebook / NotebookLM** execution sandbox (`sandbox_orchestrator`), with runtime telemetry, binary reverse-engineering, and protocol buffer schema reconstructions extracted directly from inside the live workload cell.

---

## Executive Summary

This repository presents an empirical, non-invasive systems characterization of Google's **Gemini Notebook** (formerly NotebookLM) execution sandbox. Rather than analyzing high-level prompt templates or UI behaviors, this study documents the guest execution environment from the inside out—verifying kernel syscall arbitration, supervisory process trees, inter-process communication (IPC), storage durability semantics, and virtualization containment.

The architecture comprises four primary operational layers:

1. **Virtualization & Syscall Confinement**: A user-space application kernel (**Google gVisor / Sentry**, emulating Linux 4.19 ABI) providing multi-tenant isolation, running with characteristics consistent with the `systrap` platform engine (Tier 2 inference; ~1.2 µs syscall trap latency), zero hypervisor signature on CPUID leaf `0x40000000`, an enforced device-level network air-gap (`ENETUNREACH`), zero Linux capabilities (`CapEff: 0x0`), and an active Yama LSM relational ptrace restriction (`ptrace_scope = 1`).
2. **Storage Subsystem**: A hybrid architecture consisting of an ephemeral root `overlayfs` combined with durable notebook workspace storage mediated over **Plan 9 (9P / Gofer)** file descriptors (FD 9) connected directly to `/workspace`.
3. **Execution Engine & Supervisory IPC**: A monolithic Go binary (`/usr/bin/entry/entry_point`) from Google3 (`assistant/boq/lamda/execution_box`) that acts as PID 1, runs as unprivileged `uid=1000(sandbox)`, exposes an internal length-prefixed Protobuf RPC interface over TCP (`192.168.1.1:8888`), and manages an in-guest Unix domain socket actuation harness (`/tmp/icb*/cb.sock`) synchronizing a stateful interactive bash subshell via `poll` and `cut` helper scripts.
4. **Protobuf Wire Protocols & Error Discrimination**: Verbatim extracted Google3 `sandbox_rpc.proto` schema (in `editions` syntax) defining the host-to-guest control plane, featuring granular error classification enums (`ALTAIR_SCHEMA_VALIDATION_ERROR`, `CONTAINER_OOM`, `CODE_EXECUTION_TIMED_OUT`) and differential filesystem export facilities.

---

## Provenance Framework & Classification

All statements, measurements, and logs in this study are categorized according to a strict three-tier evidential framework:

* **[Tier 1: Directly Observed]**: Directly measured via command execution, raw kernel outputs, binary disassembly, or filesystem inspection from within the live container session.
* **[Tier 2: Architectural Inference]**: Inferred from observed configurations, timing characteristics, code artifacts, or standard virtualization design patterns where host-side infrastructure cannot be directly queried.
* **[Tier 3: Platform Definition]**: Sourced from platform documentation, external research reports, or public disclosures; unverified from within the container boundary.

---

## Architectural Topography

```
+=============================================================================================+
|                                    1. USER / CLIENT LAYER                                   |
|   Prompt / Instructions (Web UI, API) <-----------------------> Formatted Responses / Files  |
+=============================================================================================+
                                              | HTTPS / RPC
                                              v
+=============================================================================================+
|                             2. AGENT & ORCHESTRATION LAYER                                  |
|   +-------------------------------------------------------------------------------------+   |
|   |  Gemini Agent Engine                                                                |   |
|   |  - Multi-Turn Reasoning & Tool Dispatcher (create_artifact, execute_command)         |   |
|   |  - External Context & Source Grounding (NotebookLM Knowledge Base)                  |   |
|   |  - Compute Dispatcher: Spins up ephemeral Borg container cells per session          |   |
|   +------------------------------------------+------------------------------------------+   |
+==============================================|==============================================+
                                               | Host TCP / veth (Length-Prefixed Protobuf)
                                               v
+=============================================================================================+
|                              3. HOST INFRASTRUCTURE LAYER                                   |
|   +-------------------------------------------------------------------------------------+   |
|   |  Host Node: synthetic Haswell CPUID profile (Model 63), not the physical host       |   |
|   |  - gVisor Sentry: User-space application kernel (consistent with systrap, Tier 2)   |   |
|   |  - gVisor Gofer: Mediates host filesystem I/O over Plan 9 (9P) file descriptors     |   |
|   |  - Host Supervisor Gateway: 169.254.1.1 connects inward to guest port 8888          |   |
|   +------------------------------------------+------------------------------------------+   |
+==============================================|==============================================+
                                               | Syscall Virtualization, 9P FDs (FD 9), & veth
                                               v
+=============================================================================================+
|                           4. SANDBOXED WORKLOAD CELL (container)                            |
|                                                                                             |
|   [ gVisor Security Boundary: Linux 4.19.0-gvisor | CapEff: 0x0 | 8 vCPUs | 8 GiB RAM ]     |
|                                                                                             |
|   +-------------------------------------------------------------------------------------+   |
|   |  Filesystem Hierarchy                                                               |   |
|   |  - Root (/): Ephemeral OverlayFS (writes discarded on container recycle)             |   |
|   |  - 9P Host Mounts: /workspace (FD 9, Gofer-mediated durable notebook workspace)    |   |
|   |  - In-Memory: /tmp (tmpfs)                                                          |   |
|   +-------------------------------------------------------------------------------------+   |
|                                                                                             |
|   +-------------------------------------------------------------------------------------+   |
|   |  Network Namespace                                                                  |   |
|   |  - eth0: 192.168.1.1/32 | lo: 127.0.0.1 | Zero external egress routes               |   |
|   |  - Outbound socket attempts -> ENETUNREACH (Errno 101)                              |   |
|   |  - Host Gateway Ingress: 169.254.1.1:58334 -> 192.168.1.1:8888                      |   |
|   +-------------------------------------------------------------------------------------+   |
|                                                                                             |
|   +-------------------------------------------------------------------------------------+   |
|   |  Command Execution & IPC Engine                                                     |   |
|   |                                                                                     |   |
|   |   Host Injected Command (Length-Prefixed Protobuf to :8888)                         |   |
|   |            │                                                                        |   |
|   |            ▼ (Unix Domain Socket: /tmp/icb*/cb.sock)                                |   |
|   |   +-----------------------------------------------------------------------------+   |   |
|   |   | PID 1: /usr/bin/entry/entry_point (UID 1000 sandbox, Google3 Blaze binary)  |   |   |
|   |   | Role: Monolithic orchestrator & interpreter_callback multicall binary       |   |   |
|   |   +--------------------------------------+--------------------------------------+   |   |
|   |                                          |                                          |   |
|   |                                          ▼                                          |   |
|   |   +─────────────────────────────────────────────────────────────────────────────+   |   |
|   |   | Stateful Bash Subshell (PID 11, -bash -ic)                                  |   |   |
|   |   | Actuation Loop:                                                             |   |   |
|   |   | 1. input="$(${POLL})" -> dials cb.sock via statefulness.ClientMain()        |   |   |
|   |   | 2. eval "${input}" -> executes user command                                 |   |   |
|   |   | 3. "${CUT}" "$exit_code" -> returns exit status to cb.sock                  |   |   |
|   |   +─────────────────────────────────────────────────────────────────────────────+   |   |
|   +-------------------------------------------------------------------------------------+   |
+=============================================================================================+
```

---

## Research Tracks

The dissection is organized across three primary tracks:

* 📁 **[Part 1: The Cage — Sandbox Confinement, Storage & Syscall Mediation](part1-the-cage/)**:
  User-space system call virtualization via gVisor (Sentry), behavioral indicators consistent with the `systrap` platform engine (~1.2 µs trap latency; Tier 2 inference), CPUID leaf `0x40000000` masking, Plan 9 (9P) Gofer descriptor mediation (FD 9), `mmap`/`msync` page cache coherency benchmarks (56.3 µs), symlink escape containment, and zero-route air-gap isolation.
* 📁 **[Part 2: The Machinery — Binary Architecture, Orchestrator Lifecycle & IPC](part2-the-machinery/)**:
  The monolithic Go binary (`/usr/bin/entry/entry_point`) from Google3 (`assistant/boq/lamda/execution_box`), dual-role `os.Args` dispatch (`interpreter_callback`), in-guest Unix domain socket actuation harness (`cb.sock`), `poll`/`cut` synchronization stubs, and full inventory of the 661-package Debian Bookworm document synthesis workbench.
* 📁 **[Part 3: The Mind — Wire Protocol, Protobuf Schemas & Security Boundary](part3-the-mind/)**:
  Verbatim reconstructed Google3 `sandbox_rpc.proto` schema (in `editions` syntax), length-prefixed binary wire framing, granular error discriminators (`ALTAIR_SCHEMA_VALIDATION_ERROR`, `CONTAINER_OOM`), Yama LSM relational attachment enforcement (`ptrace_scope = 1`), and capability bitmask analysis.

---

## Comparative Matrix: Google Jules vs. Gemini Spark vs. Gemini Notebook vs. Meta Muse

| Architectural Dimension | Google Jules Devbox | Gemini Spark Sandbox (Config A)* | Gemini Notebook (This Runtime) | Meta Muse Secure VM |
| :--- | :--- | :--- | :--- | :--- |
| **Virtualization Primitive** | Hardware VM (**KVM**) | Syscall Emulation (**gVisor**) | Syscall Emulation (**gVisor / Sentry**) | Hardware MicroVM (**KVM**) |
| **Hypervisor / Platform** | **AWS Firecracker** (`pci=off`) | gVisor Gofer + Sentry | **gVisor Sentry** (consistent with `systrap`, Tier 2) | **Cloud Hypervisor** (CPU model unverified) |
| **Privilege Model** | `jules` (UID 1001) + sudo | `spark` (UID 1235), `CapEff: 0x0` | `sandbox` (UID 1000), `CapEff: 0x0` | `root` via user namespace (`uid 0 -> 131072`) |
| **Network Egress** | Open HTTPS/UDP (GitHub, npm) | Strict Air-Gap (zero routes) | **Strict Air-Gap** (`ENETUNREACH`) | RFC 2544 VIPs (`198.18.0.0/15`) + TLS Proxy |
| **Host-to-Guest IPC** | Virtio-VSOCK / TCP port 22 | Host `runsc exec` -> `/tmp/shell.sock` | **Length-Prefixed Protobuf** on port 8888 | AF_VSOCK port 512 |
| **Execution Supervisor** | Persistent tmux + file FIFOs | In-memory FastAPI (`dynamo_exec.py`) | Monolithic Go (`sandbox_orchestrator`) | Rust multicall (`hatch-multicall`) |
| **Guest Actuation** | `inotifywait` on `/run/.../stamp` | HTTP POST `/execute_bash` | **Unix Socket Harness (`cb.sock`) via `poll`/`cut`** | `spawnd` / hatch supervisor (unverified) |
| **Storage Architecture** | SquashFS + ext4 scratch | Ephemeral overlay + 9P mounts | **Ephemeral overlay + 9P Gofer (`/workspace`)** | Btrfs on device-mapper (`zstd:3`) |
| **Process Tracing (ptrace)** | standard kernel ptrace (no sandbox emulation) | gVisor emulated | **Yama Enforced (`ptrace_scope = 1`)** | Restricted (unverified from inside container) |

*\*Note: Gemini Spark has two documented runtime configurations: Config A (gVisor + 9P, shown above) and Config B (Cloud Hypervisor microVM + Docker + XFS).*

---

## Repository Structure

```
.
├── LICENSE
├── README.md                            # Executive Summary, Architecture Topography, Matrix
├── part1-the-cage/                      # Track 1: Systems & Confinement Whitepaper
│   ├── README.md                        # Full systems whitepaper (gVisor, systrap, 9P, Air-Gap)
│   ├── evidence/                        # Raw empirical probe logs & procfs captures
│   │   ├── proc_cpuinfo.txt             # Synthetic 8-vCPU Haswell core descriptions
│   │   ├── proc_meminfo.txt             # Dynamic page accounting tables (MemTotal: 8 GiB)
│   │   ├── proc_mounts.txt              # Mount table documenting 9P Gofer on FD 9
│   │   ├── proc_net_route.txt           # Zero-route routing table
│   │   ├── proc_net_tcp.txt             # Port 8888 listener bindings
│   │   ├── proc_self_status.txt         # CapEff: 0x0 and zero capability bitmasks
│   │   └── proc_self_uid_map.txt        # Synthetic 32-bit identity mapping
│   └── scripts/                         # Standalone reproduction probes
│       ├── probe_systrap_kvm.py         # Syscall timing calibration benchmark & seccomp/sysemu probe
│       ├── probe_ptrace_scope.py        # Full Yama relational ptrace validation (PID 1, child, parent)
│       ├── probe_9p_fs.py               # Synchronous fsync IOPS benchmark
│       ├── probe_mmap_msync.py          # 9P mmap MAP_SHARED msync latency and coherency probe
│       └── probe_symlink_traversal.py   # Symlink escape testing (/etc/passwd, ../../) and EXDEV probe
├── part2-the-machinery/                 # Track 2: Binary Architecture, Orchestrator & IPC
│   ├── README.md                        # PID 1 analysis, dual-role dispatch, cb.sock harness
│   ├── data/                            # Installed package manifests & history
│   │   ├── dpkg_list.txt                # Census of all 661 Debian Bookworm packages
│   │   ├── dpkg_install_history.log     # Image build timestamps
│   │   └── pip_list.txt                 # Full Python 3.12 scientific data science stack
│   └── harness/                         # Actuation harness scripts extracted from /tmp
│       ├── poll.sh                      # Shebang script dispatching to interpreter_callback
│       └── cut.sh                       # Exit code reporting script
├── part3-the-mind/                      # Track 3: Protobuf Wire Protocols & Security
│   ├── README.md                        # Protocol buffer analysis, error enums, security model
│   └── schemas/                         # Verbatim reconstructed Protocol Buffer definitions
│       └── sandbox_rpc.proto            # Reconstructed google3 sandbox_rpc.proto (editions)
├── evidence/                            # Unified diagnostic logs (mirrors procfs & system dumps)
└── scripts/                             # Complete test suite (mirrors all reproduction probes)
```

---

## Methodology & Safety

All measurements and logs in this study were performed via non-invasive, in-situ systems diagnostics from within an authorized container session. No exploits were attempted, no host boundaries were breached, and all user-specific session paths (`c_<hex>`) and identifiers have been sanitized.

---

## About sys-dissect

**sys-dissect** is an independent systems research initiative dedicated to the empirical dissection, boundary verification, and containment analysis of production AI runtimes and autonomous agent infrastructure.

### Research Principles
* **Measure Runtime Realities:** Architecture blueprints and design disclosures present intended models; empirical probing verifies actual kernel filters, hypervisor mediation, and storage behavior.
* **Zero-Trust Boundary Analysis:** Model token streams and prompt wrappers are never trusted for authorization; isolation guarantees must be physically enforced out-of-band by the operating system, container runtime, and hypervisor.
* **Responsible & Non-Invasive:** All diagnostics are conducted via bounded, black-box inspection inside authorized workload sessions. No exploits are staged, no host boundaries are breached, and all proprietary tokens or user telemetry are strictly sanitized before publication.

---

## License & Attribution

Published by [sys-dissect](https://github.com/sys-dissect). Released under the MIT License.
