with open('dashboard_a.html', encoding='utf-8') as f:
    html = f.read()

# Find SECOND script section (inline data)
first_script_end = html.find('</script>') + len('</script>')
start = html.find('<script>', first_script_end) + len('<script>')
end = html.find('</script>', start)
js = html[start:end]

print(f'JS section length: {len(js)} chars')
print(f'Has var TREND: {"var TREND = {" in js}')
print(f'Has var SA: {"var SA = [" in js}')
print(f'Has var PIE: {"var PIE = [" in js}')
print(f'Has var SCAT: {"var SCAT = [" in js}')
print(f'Has var KAREV: {"var KAREV = {" in js}')
print(f'Has var B_CUSTS: {"var B_CUSTS = [" in js}')
print(f'Has var B_TREND: {"var B_TREND = {" in js}')
print(f'Has function switchTab: {"function switchTab" in js}')
print(f'Has function buildMain: {"function buildMain" in js}')
print(f'Has function buildPie: {"function buildPie" in js}')
print(f'Has double braces: {"{{" in js}')
# Check YRS line
idx = js.find('var YRS')
if idx >= 0:
    snippet = js[idx:idx+60]
    print(f'YRS snippet: {repr(snippet)}')
