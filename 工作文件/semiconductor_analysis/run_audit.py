import subprocess, sys
r=subprocess.run([sys.executable, r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\audit.py"],
                 capture_output=True, text=True, encoding='utf-8', errors='replace')
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\audit_err.txt","w",encoding="utf-8").write("RC:"+str(r.returncode)+"\n"+r.stderr[:1500])
print(r.returncode)
