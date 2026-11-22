import ctypes
import os
import sys
import time

libc = ctypes.CDLL(None, use_errno=True)

PTRACE_TRACEME = 0
PTRACE_ATTACH = 16
PTRACE_SEIZE = 0x4206

print("=== YAMA PTRACE PROBE ===")
try:
    with open("/proc/sys/kernel/yama/ptrace_scope") as f:
        print(f"Yama ptrace_scope: {f.read().strip()}")
except Exception as e:
    print(f"Failed to read yama/ptrace_scope: {e}")

# 1. PTRACE_ATTACH on PID 1
ret_attach = libc.ptrace(PTRACE_ATTACH, 1, 0, 0)
err_attach = ctypes.get_errno()
print(f"PTRACE_ATTACH to PID 1: ret={ret_attach}, errno={err_attach}")

# 2. PTRACE_SEIZE on PID 1
ret_seize = libc.ptrace(PTRACE_SEIZE, 1, 0, 0)
err_seize = ctypes.get_errno()
print(f"PTRACE_SEIZE to PID 1: ret={ret_seize}, errno={err_seize}")

# 3. Child PTRACE_TRACEME & Parent PTRACE_ATTACH to Child
pipe_r, pipe_w = os.pipe()
pid = os.fork()

if pid == 0:
    # Child
    os.close(pipe_r)
    ret_traceme = libc.ptrace(PTRACE_TRACEME, 0, 0, 0)
    err_traceme = ctypes.get_errno()
    os.write(pipe_w, f"{ret_traceme}:{err_traceme}".encode())
    os.close(pipe_w)
    # Wait for parent before exiting
    time.sleep(1)
    os._exit(0)
else:
    # Parent
    os.close(pipe_w)
    res = os.read(pipe_r, 64).decode()
    os.close(pipe_r)
    ret_t, err_t = res.split(":")
    print(f"Child PTRACE_TRACEME: ret={ret_t}, errno={err_t}")
    
    # Wait for child to exit
    os.waitpid(pid, 0)

# 4. Parent attaching to direct child
pid2 = os.fork()
if pid2 == 0:
    time.sleep(1)
    os._exit(0)
else:
    time.sleep(0.05)
    ret_parent = libc.ptrace(PTRACE_ATTACH, pid2, 0, 0)
    err_parent = ctypes.get_errno()
    print(f"Parent PTRACE_ATTACH to child (PID {pid2}): ret={ret_parent}, errno={err_parent}")
    os.waitpid(pid2, 0)
