import json

with open('data/b_custs.json', encoding='utf-8') as f:
    data = json.load(f)

issues = []
for c in data:
    for k, v in c.items():
        if isinstance(v, str):
            if '</script>' in v.lower():
                issues.append(f'{c["id"]}: {k} has script tag')
            if '\n' in v:
                pass  # newlines in strategy text are normal, json.dumps handles them
            if '\r' in v:
                issues.append(f'{c["id"]}: {k} has \\r')

if issues:
    for i in issues[:10]:
        print(i)
else:
    print('No critical issues found')

print(f'Checked {len(data)} customers')

# Check for XML/HTML special chars in names
bad_names = []
for c in data:
    name = c.get('n', '')
    if '&' in name or '<' in name or '>' in name:
        bad_names.append(name)
if bad_names:
    print(f'Bad names: {bad_names[:5]}')
else:
    print('All names clean')
