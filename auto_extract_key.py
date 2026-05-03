import os
import subprocess
import re
import time

def get_wechat_pid():
    try:
        pid = subprocess.check_output(["pgrep", "-x", "WeChat"]).decode("utf-8").strip()
        return pid
    except subprocess.CalledProcessError:
        return None

def extract_key():
    pid = get_wechat_pid()
    if not pid:
        print("WeChat is not running.")
        return None

    # lldb commands to extract the key
    # For ARM64, the key is in x1. For x86_64, it's in rsi.
    # We will print both just in case.
    lldb_cmds = f"""
    process attach --pid {pid}
    br set -n sqlite3_key
    c
    memory read --size 1 --format x --count 32 $x1
    memory read --size 1 --format x --count 32 $rsi
    q
    """
    
    with open("/tmp/wechat_lldb_script.txt", "w") as f:
        f.write(lldb_cmds)

    print("Please log out of WeChat on your Mac and log back in. Waiting for the breakpoint to hit...")
    
    # Run lldb with administrator privileges via osascript
    # This will prompt the user with a GUI for their password
    apple_script = f'''
    do shell script "lldb -s /tmp/wechat_lldb_script.txt" with administrator privileges
    '''
    
    try:
        output = subprocess.check_output(["osascript", "-e", apple_script]).decode("utf-8")
        return output
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    out = extract_key()
    if out:
        with open("/tmp/wechat_key_output.txt", "w") as f:
            f.write(out)
        print("Key extraction output saved to /tmp/wechat_key_output.txt")
