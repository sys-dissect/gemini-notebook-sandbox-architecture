import ctypes
import os
import mmap
import time

libc = ctypes.CDLL(None, use_errno=True)

print("=== SYSTRAP & PLATFORM ENGINE PROBES ===")

# 1. Syscall getpid latency benchmark
SYS_getpid = 39
iterations = 50000
start = time.perf_counter_ns()
for _ in range(iterations):
    libc.syscall(SYS_getpid)
elapsed = time.perf_counter_ns() - start
avg_latency_ns = elapsed / iterations
print(f"1. Syscall getpid avg latency: {avg_latency_ns:.2f} ns (reference: ~50-80ns bare-metal, ~1000-1500ns Sentry systrap)")

# 2. CPUID Leaf 0x40000000 (Hypervisor Signature) via executable memory buffer
# Assembly:
#   mov %rdi, %r8   (save buf ptr)
#   mov %esi, %eax   (leaf)
#   cpuid
#   mov %eax, 0(%r8)
#   mov %ebx, 4(%r8)
#   mov %ecx, 8(%r8)
#   mov %edx, 12(%r8)
#   ret
code = (
    b"\x49\x89\xf8"          # mov %rdi, %r8
    b"\x89\xf0"              # mov %esi, %eax
    b"\x31\xc9"              # xor %ecx, %ecx
    b"\x0f\xa2"              # cpuid
    b"\x41\x89\x00"          # mov %eax, 0(%r8)
    b"\x41\x89\x58\x04"      # mov %ebx, 4(%r8)
    b"\x41\x89\x48\x08"      # mov %ecx, 8(%r8)
    b"\x41\x89\x50\x0c"      # mov %edx, 12(%r8)
    b"\xc3"                  # ret
)

buf = mmap.mmap(-1, 4096, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS, prot=mmap.PROT_READ | mmap.PROT_WRITE)
buf.write(code)

PROT_READ = 1
PROT_WRITE = 2
PROT_EXEC = 4
libc.mprotect(ctypes.c_void_p(ctypes.addressof(ctypes.c_char.from_buffer(buf))), 4096, PROT_READ | PROT_EXEC)

proto = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32)
cpuid_func = proto(ctypes.addressof(ctypes.c_char.from_buffer(buf)))

res_buf = (ctypes.c_uint32 * 4)()
cpuid_func(ctypes.byref(res_buf), 0x40000000)

sig_bytes = bytes(res_buf)[4:16]
sig_clean = "".join(f"\\x{b:02x}" if (b < 32 or b > 126) else chr(b) for b in sig_bytes)
print(f"2. CPUID(0x40000000) eax=0x{res_buf[0]:x}, sig bytes={sig_clean} (Sentry masks/zeroes hypervisor leaf)")

# 3. PTRACE_SYSEMU probe on traced child
PTRACE_TRACEME = 0
PTRACE_SYSEMU = 31

pipe_r, pipe_w = os.pipe()
pid = os.fork()

if pid == 0:
    os.close(pipe_r)
    libc.ptrace(PTRACE_TRACEME, 0, 0, 0)
    os.close(pipe_w)
    # Stop itself to allow parent to trace
    os.kill(os.getpid(), 19) # SIGSTOP
    os._exit(0)
else:
    os.close(pipe_w)
    os.waitpid(pid, 0) # Wait for child SIGSTOP
    ret_sysemu = libc.ptrace(PTRACE_SYSEMU, pid, 0, 0)
    err_sysemu = ctypes.get_errno()
    print(f"3. PTRACE_SYSEMU on child: ret={ret_sysemu}, errno={err_sysemu} (supported by Sentry)")
    # Let child exit
    libc.ptrace(17, pid, 0, 0) # PTRACE_DETACH
    os.waitpid(pid, 0)

# 4. Strict seccomp transition probe
SYS_seccomp = 317
SECCOMP_SET_MODE_STRICT = 0
ret_seccomp = libc.syscall(SYS_seccomp, SECCOMP_SET_MODE_STRICT, 0, None)
err_seccomp = ctypes.get_errno()
print(f"4. SYS_seccomp(SECCOMP_SET_MODE_STRICT): ret={ret_seccomp}, errno={err_seccomp} (EINVAL=22; Sentry stubs nested seccomp)")
