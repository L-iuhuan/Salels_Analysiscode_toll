html = open('dashboard_a.html', encoding='utf-8').read()
checks = [
    ('YRS braces', 'var YRS = {2024: true, 2025: true, 2026: true};' in html),
    ('BSORT braces', "var BSORT = {key: 'r', asc: false};" in html),
    ('switchTab function', 'function switchTab(t) {' in html),
    ('buildMain function', 'function buildMain() {' in html),
    ('formatter newline', r"formatter: '{b}\n{d}%'" in html or "formatter: '{b}\\n{d}%'" in html),
    ('no KPI placeholder', '%%KPI_R%%' not in html),
    ('no LATEST placeholder', '%%LATEST%%' not in html),
    ('no DATA placeholder', '%%DATA_BLOCK%%' not in html),
    ('ALL = B_CUSTS', 'ALL = B_CUSTS;' in html or 'var ALL = B_CUSTS' in html),
]
for name, ok in checks:
    print(f"  {'OK' if ok else 'FAIL'} {name}")
