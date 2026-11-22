import os
import errno

test_dir = "/workspace/scratch/symlink_probe"
os.makedirs(test_dir, exist_ok=True)

# 1. Absolute symlink to /etc/passwd
link_abs = os.path.join(test_dir, "link_passwd_abs")
if os.path.exists(link_abs):
    os.remove(link_abs)
os.symlink("/etc/passwd", link_abs)

with open(link_abs, "r") as f:
    line_abs = f.readline().strip()
print(f"1. Absolute symlink to /etc/passwd reads: {line_abs.split(':')[0]} (resolves inside container rootfs)")

# 2. Relative dot-dot chain escaping 9P mount
link_rel = os.path.join(test_dir, "link_passwd_rel")
if os.path.exists(link_rel):
    os.remove(link_rel)
os.symlink("../../../../../../../../../etc/passwd", link_rel)

with open(link_rel, "r") as f:
    line_rel = f.readline().strip()
print(f"2. Relative ../../../etc/passwd reads: {line_rel.split(':')[0]} (trapped within container rootfs)")

# 3. In-tree hardlink test
file_src = os.path.join(test_dir, "hardlink_src.txt")
file_dst = os.path.join(test_dir, "hardlink_dst.txt")
with open(file_src, "w") as f:
    f.write("hardlink test")

if os.path.exists(file_dst):
    os.remove(file_dst)
os.link(file_src, file_dst)
st_src = os.stat(file_src)
st_dst = os.stat(file_dst)
print(f"3. In-tree 9P hardlink: src_ino={st_src.st_ino}, dst_ino={st_dst.st_ino}, nlink={st_dst.st_nlink} (supported)")

# 4. Cross-filesystem hardlink test (/etc/issue -> /workspace)
cross_dst = os.path.join(test_dir, "cross_link.txt")
if os.path.exists(cross_dst):
    os.remove(cross_dst)
try:
    os.link("/etc/issue", cross_dst)
    print("4. Cross-fs link: unexpectedly succeeded")
except OSError as e:
    print(f"4. Cross-fs hardlink from /etc to /workspace correctly rejected: errno={e.errno} ({errno.errorcode.get(e.errno, 'UNKNOWN')})")

# Clean up
os.remove(link_abs)
os.remove(link_rel)
os.remove(file_dst)
os.remove(file_src)
os.rmdir(test_dir)
