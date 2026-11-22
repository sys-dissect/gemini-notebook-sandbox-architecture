# Part 2: The Machinery — Binary Architecture, Orchestrator & IPC

## Overview
Part 2 deconstructs the internal execution supervisor, dual-role multicall binary, and in-guest inter-process communication harness that powers Gemini Notebook's command execution.

## 1. Monolithic Google3 Orchestrator (`entry_point`)
* **Binary**: `/usr/bin/entry/entry_point` (13,838,480 bytes, ELF 64-bit LSB, statically linked).
* **Provenance**: Compiled via Google Blaze targeting `k8-opt` from Google3 source tree:
  `google3/assistant/boq/lamda/execution_box/images/sandbox_orchestrator/`
* **Unstripped Debug Data**: Contains full `.symtab` (16,958 symbols) and complete DWARF debug info (`.debug_info`, `.debug_line`).
* **Dual-Role Dispatch**:
  * At offset `0x8538cd`, `orchestrator.Run` inspects `os.Args[0]`.
  * If invoked as `"interpreter_callback"`, it branches immediately to `statefulness.ClientMain()` and exits.
  * If invoked as `entry_point`, it initializes the daemon, binds to `192.168.1.1:8888`, and spawns the stateful subshell.

## 2. In-Guest Actuation Harness (`cb.sock`)
* Orchestrator serves a local Unix domain stream socket at `/tmp/icb<id>/cb.sock`.
* The stateful interactive bash subshell (`PID 11`, `-bash -ic`) evaluates commands using two 39-byte helper stubs:
  1. `poll`: Executes `interpreter_callback`, connects to `cb.sock`, reads the pending command from the host, and emits it to stdout.
  2. `cut`: Executes `interpreter_callback`, connects to `cb.sock`, writes the numeric exit code, and half-closes the connection.

## 3. Package Manifests & Tooling Stack
* 661 Debian Bookworm packages providing document synthesis (LaTeX, Poppler, Pandoc, headless LibreOffice/UNO bindings, FFmpeg, ImageMagick).
* Comprehensive Python 3.12 data science stack.

## Files
* `harness/poll.sh`: Exact 39-byte shebang dispatch stub for polling commands.
* `harness/cut.sh`: Exact 39-byte shebang dispatch stub for returning exit codes.
* `data/dpkg_list.txt`: Census of all installed system packages.
* `data/pip_list.txt`: Python package inventory.
* `data/dpkg_install_history.log`: Image build timestamps.
