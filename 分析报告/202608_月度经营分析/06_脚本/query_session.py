# -*- coding: utf-8 -*-
"""只读查询：当前会话（C:/Users/910373 目录下最近活跃的父会话）id 与标题"""
import sqlite3

con = sqlite3.connect(r"file:C:/Users/910373/.local/share/opencode/opencode.db?mode=ro", uri=True)
rows = con.execute(
    "SELECT id, title, time_updated FROM session "
    "WHERE directory = 'C:/Users/910373' AND parent_id IS NULL AND time_archived IS NULL "
    "ORDER BY time_updated DESC LIMIT 3"
).fetchall()
import datetime
for r in rows:
    ts = r[2] / 1000 if r[2] > 10**12 else r[2]
    print(r[0], "|", (r[1] or "(无标题)")[:60], "|", datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M"))
con.close()
