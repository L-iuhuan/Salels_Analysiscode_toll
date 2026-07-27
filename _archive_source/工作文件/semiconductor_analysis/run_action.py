import subprocess, sys
r=subprocess.run([sys.executable, r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\deep_action.py"],
                 capture_output=True, text=True, encoding='utf-8', errors='replace')
open(r"C:\Users\45091\Desktop\工作文件\semiconductor_analysis\deep_action_err.txt","w",encoding="utf-8").write(
    "RC:"+str(r.returncode)+"\nSTDOUT:\n"+(r.stdout or "")[-200:]+"\n\nSTDERR:\n"+(r.stderr or "")[-2500:])
print("rc",r.returncode)
