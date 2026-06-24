import subprocess, json, sys
r = subprocess.run(["python", "-m", "pytest", "tests/", "-x", "-q", "--timeout", "60"], capture_output=True, text=True)
s = 1.0 if r.returncode == 0 else 0.0
json.dump({"composite": s, "dimensions": {"tests": {"score": s, "weight": 1.0}}}, sys.stdout)
