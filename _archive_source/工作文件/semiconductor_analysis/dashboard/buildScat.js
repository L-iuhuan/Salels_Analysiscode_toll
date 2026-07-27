function buildScat() {
  var c = initCh('scatter');
  if (!c) return;
  var mgs = SCAT.map(function(d) { return d.mg; }).sort(function(a, b) { return a - b; });
  var mgn = mgs.length > 0 ? mgs[Math.floor(mgs.length / 2)] : 0;
  var data = SCAT.map(function(d) {
    return { value: [d.g, d.mg, Math.max(d.rev, 1)], name: d.n, dual: d.d };
  });
  c.setOption({
    tooltip: {
      trigger: 'item',
      formatter: function(p) {
        return p.name + '<br/>销售额增长:' + p.value[0] + '%<br/>毛利率:' + p.value[1] + '%<br/>YTD收入:' + Math.round(p.value[2]) + '万<br/>' + p.dual;
      }
    },
    grid: {left: 55, right: 20, top: 15, bottom: 35},
    xAxis: { type: 'value', name: 'YTD同比销售额增长率%', nameLocation: 'center', nameGap: 35, axisLabel: {fontSize: 9},
      scale: true, splitLine: {show: true, lineStyle: {type: 'dashed', color: '#e5e7eb'}} },
    yAxis: { type: 'value', name: 'YTD毛利率%', nameLocation: 'center', nameGap: 40, axisLabel: {fontSize: 9},
      scale: true, splitLine: {show: true, lineStyle: {type: 'dashed', color: '#e5e7eb'}} },
    series: [{
      type: 'scatter', data: data,
      symbolSize: function(d) { return Math.max(6, Math.sqrt(d[2]) * 1.5); },
      itemStyle: {
        color: function(p) {
          var g = p.value[0], m = p.value[1];
          if (m >= mgn && g < 0) return '#3b82f6';
          if (m < mgn && g >= 0) return '#ea580c';
          if (m >= mgn && g >= 0) return '#16a34a';
          return '#9ca3af';
        }, opacity: 0.75
      },
      markLine: {
        silent: true,
        data: [
          { yAxis: mgn, name: '毛利率中位 ' + mgn.toFixed(1) + '%',
            label: {formatter: '中位 ' + mgn.toFixed(1) + '%'}, lineStyle: {color: '#888', type: 'dashed'} },
          { xAxis: 0, name: '持平', lineStyle: {color: '#888', type: 'dashed'} }
        ]
      }
    }]
  });
  c.on('click', function(p) { openB(p.name); });
}