# -*- coding: utf-8 -*-
"""阶段六b:重组 recession_risk_opt 分支结构以匹配脚本的路径假设:
脚本假设自己位于 <根>/recession_risk_opt/ 下,输入在 <根>/output/silver/。
"""
import os, shutil

B = r"E:\3-其他资料\数据分析\project_branches\recession_risk_opt"
SUB = os.path.join(B, "recession_risk_opt")
KEEP = {"README.md", "requirements.txt", "run.bat", "run.sh", "test_smoke.py", "output", "recession_risk_opt"}

os.makedirs(SUB, exist_ok=True)
moved = []
for name in os.listdir(B):
    if name in KEEP:
        continue
    src = os.path.join(B, name)
    dst = os.path.join(SUB, name)
    if os.path.exists(dst):
        continue
    shutil.move(src, dst)
    moved.append(name)
print("moved:", moved)
