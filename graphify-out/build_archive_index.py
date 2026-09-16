# -*- coding: utf-8 -*-
"""归档文档编目：扫描归档区 md/txt，按主题分组，抽头部摘要，生成 ARCHIVE_DOC_INDEX.md"""
import os
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path('.')
ARCHIVE_DIRS = ['_archive_source', '_deprecated', 'qa_tool_old']
OUT = ROOT / 'graphify-out' / 'ARCHIVE_DOC_INDEX.md'

def classify(rel):
    s = rel.replace('\\', '/').lower()
    rules = [
        (('experiment_log', 'exp_', '实验日志'), '实验日志与设计'),
        (('预测', 'forecast', 'quarterly', 'eda'), '预测方法与实验'),
        (('因子', 'factor', '调优', 'calibration', '校准'), '因子工程与调优'),
        (('客户', 'customer', '品类', 'category', '关联规则', 'b2b'), '客户与品类分析'),
        (('生命周期', 'lifecycle', '产品线'), '产品生命周期'),
        (('风险', 'risk', 'recession', '预警', '异动'), '风险与异动预警'),
        (('看板', 'dashboard', 'pipeline', '管道', 'kpi', '数据质量', '白皮书', '维护手册', '血缘', '重构', '架构', '策略'), '数据管道与看板工程'),
        (('测试', '验证', 'test', 'review', '审查', '问题清单', 'diag', 'readme', '使用说明', '说明'), '说明与测试治理'),
        (('session', '备份', 'backup', '对比'), '会话记录与备份'),
    ]
    for keys, cat in rules:
        if any(k in s for k in keys):
            return cat
    return '项目散文档'

EXCLUDE = ('.venv', 'site-packages', 'node_modules', '.git')
groups = defaultdict(list)
total = 0
for d in ARCHIVE_DIRS:
    base = ROOT / d
    if not base.exists():
        continue
    for p in base.rglob('*'):
        if p.suffix.lower() not in ('.md', '.txt'):
            continue
        if any(x in str(p) for x in EXCLUDE):
            continue
        rel = p.relative_to(ROOT)
        size = p.stat().st_size
        lines = 0
        head = ''
        try:
            with open(p, encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f):
                    lines += 1
                    if i < 12:
                        t = line.strip().lstrip('#').strip()
                        if t and len(t) > 6 and not head:
                            head = t[:70]
        except Exception:
            pass
        groups[classify(str(rel))].append((str(rel), size, lines, head))
        total += 1

ORDER = ['预测方法与实验', '实验日志与设计', '因子工程与调优', '客户与品类分析', '产品生命周期', '风险与异动预警',
         '数据管道与看板工程', '说明与测试治理', '会话记录与备份', '项目散文档']
L = ['# 归档文档索引（ARCHIVE_DOC_INDEX）', '',
     '> 生成于 2026-09-16。归档区 = 搁置的方案库（非死代码）：曾完成的工作，后因专注看板流水线而搁置。',
     '> **用法**：按主题区块扫卡片 → 锁定 2-3 篇 → 精读原文。卡片格式：`路径 ｜ 规模 ｜ 开篇摘要`。',
     '> 共 %d 篇文档。做预测任务先查「预测方法与实验」「因子工程与调优」两块。' % total, '']
for cat in ORDER:
    items = groups.get(cat, [])
    if not items:
        continue
    items.sort(key=lambda x: -x[1])
    L.append('## %s（%d 篇）' % (cat, len(items)))
    L.append('')
    for rel, size, lines, head in items:
        kb = size // 1024
        L.append('- `%s` ｜ %dKB/%d行 ｜ %s' % (rel.replace('\\', '/'), kb, lines, head or '—'))
    L.append('')
L.append('---')
L.append('*维护：归档新增文档后重跑 `复核脚本无 → 临时脚本 build_archive_index.py（graphify-out 生成器）`；主题规则在脚本 classify() 中。*')
OUT.write_text('\n'.join(L), encoding='utf-8')
print('总文档: %d' % total)
for cat in ORDER:
    print('  %-14s %d' % (cat, len(groups.get(cat, []))))
print('已写: %s' % OUT)
