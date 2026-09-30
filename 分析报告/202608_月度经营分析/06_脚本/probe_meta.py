import glob, os
path = max(glob.glob(r'E:\3-其他资料\数据分析\sales_analytics_platform\output\dashboard\销售数据分析看板_*.html'), key=os.path.getmtime)
html = open(path, encoding='utf-8').read()
meta = 'id="faceMetaA"'
start = html.find(meta)
end = html.find('id="faceMeta', start+1)
print('start', start, 'end', end)
print(repr(html[start:end]))
print('---next search from', start+1)
print(repr(html[start:start+100]))
