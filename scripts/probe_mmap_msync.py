import os
import mmap
import time
import ctypes

libc = ctypes.CDLL(None, use_errno=True)

test_dir = "/workspace/scratch/mmap_probe"
os.makedirs(test_dir, exist_ok=True)
test_file = os.path.join(test_dir, "mmap_9p_test.bin")

# Create a 64KB file
size = 64 * 1024
with open(test_file, "wb") as f:
    f.write(b"A" * size)

# Open and mmap with MAP_SHARED
fd = os.open(test_file, os.O_RDWR)
mm = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

# Modify byte via memory map
mm[0:4] = b"TEST"

# Measure msync latency
MS_SYNC = 4
mm_ptr = ctypes.c_void_p(ctypes.addressof(ctypes.c_char.from_buffer(mm)))

trials = 100
latencies = []
for _ in range(trials):
    mm[0:4] = b"SYNC"
    t0 = time.perf_counter_ns()
    ret = libc.msync(mm_ptr, size, MS_SYNC)
    t1 = time.perf_counter_ns()
    if ret == 0:
        latencies.append((t1 - t0) / 1000.0)

avg_msync_us = sum(latencies) / len(latencies)
print(f"1. 9P mmap MAP_SHARED msync(MS_SYNC) avg latency: {avg_msync_us:.2f} us (over {trials} trials)")

# Check cache coherency via independent read()
fd2 = os.open(test_file, os.O_RDONLY)
read_val = os.read(fd2, 4)
os.close(fd2)
coherent = (read_val == b"SYNC")
print(f"2. 9P Page Cache Coherency (read back from independent fd): {read_val} -> Coherent: {coherent}")

# Test MAP_PRIVATE copy-on-write
mm_priv = mmap.mmap(fd, size, mmap.MAP_PRIVATE, mmap.PROT_READ | mmap.PROT_WRITE)
mm_priv[0:4] = b"COW!"
fd3 = os.open(test_file, os.O_RDONLY)
read_val_priv = os.read(fd3, 4)
os.close(fd3)
cow_intact = (read_val_priv == b"SYNC")
print(f"3. 9P MAP_PRIVATE Copy-on-Write intact (file remains unchanged): {cow_intact}")

mm_priv.close()
mm.close()
os.close(fd)
os.remove(test_file)
os.rmdir(test_dir)
