import os
import subprocess
import time

def find_wechat_pid():
    try:
        pid = subprocess.check_output(["pgrep", "-x", "WeChat"]).decode("utf-8").strip()
        return pid
    except subprocess.CalledProcessError:
        return None

print("WeChat Key Extractor for Mac")
print("----------------------------")
print("If WeChat is currently running, we need to restart it to capture the encryption key when it loads the databases.")
print("Waiting for WeChat to be launched...")

# Wait until WeChat is running
pid = None
while not pid:
    pid = find_wechat_pid()
    if not pid:
        time.sleep(1)

print(f"Found WeChat process with PID: {pid}")
print("Attaching debugger... (This may require sudo if it fails)")

# We will use lldb to attach and break on sqlite3_key
# Since WeChat 4.x has multiple databases, we might hit the breakpoint multiple times.
# We will just print the first few keys we find.

lldb_script = f"""
process attach --pid {pid}
br set -n sqlite3_key
c
"""

with open("/tmp/lldb_wechat.txt", "w") as f:
    f.write(lldb_script)

print("Please follow these instructions carefully:")
print("1. If WeChat is logged in, please LOG OUT first, then run this script.")
print("2. When the debugger attaches, log in to WeChat on your phone.")
print("3. When lldb breaks, you will see a (lldb) prompt.")
print("   At the prompt, type: memory read --size 1 --format x --count 32 $x1")
print("   (Or $rsi if on Intel Mac)")
print("4. Copy the hex output. That is your 32-byte key.")
print("5. Type 'c' to continue, or 'q' to quit lldb.")

try:
    # We run lldb interactively so the user can type commands
    subprocess.run(["lldb", "-s", "/tmp/lldb_wechat.txt"])
except KeyboardInterrupt:
    print("\nExiting.")
