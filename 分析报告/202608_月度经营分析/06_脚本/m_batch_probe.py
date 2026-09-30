# -*- coding: utf-8 -*-
"""M1-M4 CDP 实测：
① 金宝鑫展开无 nan 客户行 + bSelPair 全可点
② geo 弹层连点 广东↔江苏 5 次：ECharts 实例数不增 + trend=最后点击省
③ B_CUSTS 无「未知客户」零值行 + DQ 概览有统计行
"""
import glob, json, os, re, sys
from playwright.sync_api import sync_playwright

BASE = r'E:\3-其他资料\数据分析\sales_analytics_platform'
html = max(glob.glob(BASE + r'\output\dashboard\销售数据分析看板_*.html'), key=os.path.getmtime)
src = open(html, encoding='utf-8').read()
print('product:', os.path.basename(html))

def get_var(name):
    m = re.search(r'var ' + name + r' = (.*?);\n', src, re.S)
    return json.loads(m.group(1)) if m else None

B_AGENTS = get_var('B_AGENTS')
B_CUSTS = get_var('B_CUSTS')
GEO_PROVINCES = get_var('GEO_PROVINCES')
NAN = {"nan", "None", "", "未知客户"}

fails = []
def ok(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  >> ' + str(extra)[:240]) if (extra and not cond) else ''))
    if not cond: fails.append(name)

# ── ③ JSON 级（前后台同做） ──
bad_rows = [c for c in B_CUSTS if c.get('n') in NAN or c.get('id') in NAN]
ok('M1 B_CUSTS 无未知客户零值行', not bad_rows, bad_rows[:3])
pairs = (B_AGENTS.get('pairs') or {}).get('jx', {}).get('深圳市金宝鑫科技有限公司', [])
ok('M1 金宝鑫 pairs 无哨兵键', all(p['id'] not in NAN and p['n'] not in NAN for p in pairs), pairs[:2])
print('INFO  金宝鑫 pairs=%d 客户' % len(pairs))

dq = max(glob.glob(BASE + r'\output\dashboard\销售模式数据问题_*.md'), key=os.path.getmtime)
dq_txt = open(dq, encoding='utf-8').read()
m = re.search(r'无客户编号交易行（客户维度已剔除[^：]*）：(\d+) 行 / ([\d.]+) 万', dq_txt)
ok('M1 DQ 概览有剔除统计行', m is not None, dq)
if m: print('INFO  DQ: 无客户编号 %s 行 / %s 万' % (m.group(1), m.group(2)))

with sync_playwright() as pw:
    pg = pw.chromium.launch().new_page(viewport={'width': 1600, 'height': 1000})
    pg.goto('file:///' + html.replace('\\', '/'))
    pg.wait_for_timeout(900)

    # ── ① 金宝鑫展开：无 nan 行 + 全部可点 ──
    pg.evaluate("switchTab('B')")
    pg.wait_for_timeout(400)
    pg.evaluate("bSetMode('agent')")
    pg.wait_for_timeout(400)
    pg.evaluate("bSelAgent('深圳市金宝鑫科技有限公司')")
    pg.wait_for_timeout(500)
    vis = pg.evaluate("""() => {
      const rows=[...document.querySelectorAll('#bList .brow')].map(r=>r.textContent);
      return {rows: rows.length, nanRows: rows.filter(t=>/nan|未知客户|None/.test(t)).length};
    }""")
    ok('M4 金宝鑫展开列表无 nan 行', vis['nanRows'] == 0, vis)
    clicked = pg.evaluate("""(ids) => {
      const bad=[];
      ids.forEach(id=>{ try{ bSelPair(id); const det=document.getElementById('bDet').textContent.trim();
        if(det.length<20) bad.push(id+':empty'); }catch(e){ bad.push(id+':'+e.message); } });
      return {total: ids.length, bad};
    }""", [p['id'] for p in pairs])
    ok('M4 金宝鑫 pairs 全部 bSelPair 可点', clicked['total'] > 0 and not clicked['bad'], clicked['bad'][:5])
    print('INFO  bSelPair 可点 %d/%d' % (clicked['total'] - len(clicked['bad']), clicked['total']))

    # ── ② geo 连点 5 次：实例不增 + trend=最后省 ──
    pg.evaluate("switchTab('A')")
    pg.wait_for_timeout(600)
    n0 = pg.evaluate("Object.keys(TABS.ChartRegistry._byId||{}).length")
    for i in range(5):
        pg.evaluate("geoOpenDrawer('广东')")
        pg.wait_for_timeout(25)
        pg.evaluate("geoOpenDrawer('江苏')")
        pg.wait_for_timeout(25)
    pg.wait_for_timeout(700)  # 等最后一次 onOpen(100)+setTimeout(120) 完成
    n1 = pg.evaluate("Object.keys(TABS.ChartRegistry._byId||{}).length")
    ok('M2 连点5次 ECharts 注册实例数不增', n1 <= n0 + 1, {'before': n0, 'after': n1})  # +1=最后一次trend本身
    trend = pg.evaluate("""() => {
      const el=document.getElementById('geoDrawerTrend'); if(!el) return {err:'no dom'};
      const ch=echarts.getInstanceByDom(el); if(!ch) return {err:'no chart'};
      const o=ch.getOption();
      return {data:(o.series&&o.series[0]&&o.series[0].data)||[], title:document.getElementById('appDrawerTitle')?.textContent||''};
    }""")
    js_jiangsu = next((p['trend'] for p in (GEO_PROVINCES or []) if p['n'] == '江苏'), None)
    ok('M2 trend=最后点击省(江苏)', trend.get('data') == js_jiangsu, {'got_head': (trend.get('data') or [])[:3], 'exp_head': (js_jiangsu or [])[:3]})
    ok('M2 抽屉标题=江苏', '江苏' in (trend.get('title') or ''), trend.get('title'))
    print('INFO  实例 %d→%d | trend前3点=%s' % (n0, n1, (trend.get('data') or [])[:3]))

    pg.close()

print('\n== ' + ('ALL PASS' if not fails else 'FAIL(%d): %s' % (len(fails), fails)) + ' ==')
sys.exit(1 if fails else 0)
