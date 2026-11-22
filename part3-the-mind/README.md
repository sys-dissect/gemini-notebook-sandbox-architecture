# Part 3: The Mind — Protobuf Wire Protocols & Security Boundary

## Overview
Part 3 provides the complete reconstructed Google3 protocol buffer schema, length-prefixed wire protocol, and kernel security boundaries governing Gemini Notebook's execution environment.

## 1. Reconstructed Google3 Schema (`sandbox_rpc.proto`)
Extracted directly from the embedded `FileDescriptorProto` at binary offset `0x18399` in `/usr/bin/entry/entry_point`.
* **Syntax**: Google internal `editions` syntax.
* **Top-Level Message Envelopes**:
  * `SandboxIn`: Multiplexes `ExecuteCodeRequest`, `Shutdown`, `CheckReady`, and dynamic interpreter requests.
  * `SandboxOut`: Multiplexes `ReadyToExecute`, `ExecuteCodeResponse`, `NonUserError`, and interpreter responses.
* **Granular Error Discrimination**:
  * `ExitStatus`: Enums include specialized codes such as `ALTAIR_SCHEMA_VALIDATION_ERROR (112)`, confirming tailored visualization validation, alongside standard runtime exceptions (`ZERO_DIVISION_ERROR`, `SYNTAX_ERROR`).
  * `ConstraintViolation`: Distinguishes `CONTAINER_OOM (1)` and `CONSTRAINT_CODE_EXECUTION_TIMED_OUT (2)`.

## 2. Security Boundary & LSM Enforcement
* **Yama Relational Ptrace Enforced**: `/proc/sys/kernel/yama/ptrace_scope` returns `1`. Cross-process attachment to PID 1 (`entry_point`) fails with `EPERM (errno=1)` despite sharing `uid=1000(sandbox)`. Hierarchical tracing of child processes succeeds.
* **Zero Linux Capabilities**: `CapEff: 0000000000000000`. Raw network creation, device manipulation, and reboot syscalls are hard-rejected with `EPERM`.

## Files
* `schemas/sandbox_rpc.proto`: Complete, verbatim reconstructed Google3 protocol buffer schema.
