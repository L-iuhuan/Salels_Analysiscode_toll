# -*- coding: utf-8 -*-
import subprocess, sys
r = subprocess.run([sys.executable, r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\analysis3.py"],
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\err3.txt","w",encoding="utf-8").write(
    "RC:"+str(r.returncode)+"\nSTDOUT:\n"+r.stdout+"\n\nSTDERR:\n"+r.stderr[-3000:])
print("rc",r.returncode)
