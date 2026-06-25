import subprocess, json, sys, re
r = subprocess.run(['python', '-m', 'pytest', 'tests/', '-q', '--timeout', '120', '--tb=no'], capture_output=True, text=True)
m = re.search(r'(\d+) passed', r.stdout)
passed = int(m.group(1)) if m else 0
m2 = re.search(r'(\d+) failed', r.stdout)
failed = int(m2.group(1)) if m2 else 0
total = passed + failed if (passed + failed) > 0 else 1
s = passed / total
json.dump({'composite': s, 'dimensions': {'tests': {'score': s, 'weight': 1.0}}, 'details': {'passed': passed, 'failed': failed, 'total': total}}, sys.stdout)
