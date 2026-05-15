"""
Manual approval script — run from laptop to approve/reject.
Usage:
  .venv\Scripts\python.exe approve.py topic 2     # approve topic #2
  .venv\Scripts\python.exe approve.py video        # approve video
  .venv\Scripts\python.exe approve.py reject bad thumbnail  # reject with reason
"""
import sys, requests
sys.path.insert(0, '.')

BASE = "http://localhost:5055"

if len(sys.argv) < 2:
    print("Usage: approve.py topic <num> | approve.py video | approve.py reject <reason>")
    sys.exit(1)

cmd = sys.argv[1].lower()

if cmd == "topic":
    idx = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0
    r = requests.post(f"{BASE}/approve_topic?idx={idx}")
    print(r.text)

elif cmd == "video":
    r = requests.post(f"{BASE}/approve_video")
    print(r.text)

elif cmd == "reject":
    reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "rejected"
    r = requests.post(f"{BASE}/reject_video?reason={reason}")
    print(r.text)

else:
    print(f"Unknown command: {cmd}")
