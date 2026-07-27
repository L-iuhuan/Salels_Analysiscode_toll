# -*- coding: utf-8 -*-
import subprocess, sys
scripts=['ka_list.py','analysis2.py','analysis3.py']
for s in scripts:
    r=subprocess.run([sys.executable, r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\\"+s],
                     capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(s, "rc", r.returncode, "|", r.stdout.strip()[-50:] if r.stdout else "", "| ERR", r.stderr[-200:] if r.stderr else "")
