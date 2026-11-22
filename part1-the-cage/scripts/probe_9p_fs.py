import os, time

path = "/workspace/scratch/bench_9p.dat"
t0 = time.perf_counter()
with open(path, "wb") as f:
    for _ in range(1000):
        f.write(b"X" * 4096)
        f.flush()
        os.fsync(f.fileno())
t1 = time.perf_counter()
print(f"1000 synchronous 4KB fsync writes: {t1 - t0:.4f} s ({(1000 / (t1 - t0)):.2f} IOPS)")
if os.path.exists(path):
    os.unlink(path)
