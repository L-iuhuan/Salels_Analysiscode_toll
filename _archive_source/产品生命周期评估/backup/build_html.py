#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json

# 读取JSON数据
with open(r'E:\3-其他资料\产品生命周期评估\data.json', 'r', encoding='utf-8-sig') as f:
    data_str = f.read()

# 替换NaN为null
data_str = data_str.replace('NaN', 'null')

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>产品生命周期评估看板</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #333; }
        .header { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 24px; font-weight: 600; }
        .header .meta { font-size: 14px; opacity: 0.8; }
        .kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; padding: 20px 32px; }
        .kpi-card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .kpi-card .label { font-size: 13px; color: #8c8c8c; margin-bottom: 8px; }
        .kpi-card .value { font-size: 28px; font-weight: 700; color: #1e3c72; }
        .kpi-card .sub { font-size: 12px; color: #8c8c8c; margin-top: 4px; }
        .filters { background: white; margin: 0 32px 20px; border-radius: 8px; padding: 16px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
        .filters label { font-size: 13px; color: #595959; font-weight: 500; }
        .filters select { padding: 6px 12px; border: 1px solid #d9d9d9; border-radius: 4px; font-size: 13px; background: white; cursor: pointer; min-width: 140px; }
        .filters select:focus { outline: none; border-color: #2a5298; box-shadow: 0 0 0 2px rgba(42,82,152,0.2); }
        .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 0 32px 20px; }
        .chart-box { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .chart-box.full { grid-column: span 2; }
        .chart-box h3 { font-size: 16px; font-weight: 600; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0; }
        .chart { width: 100%; height: 400px; }
        .table-section { padding: 0 32px 32px; }
        .table-box { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .table-box h3 { font-size: 16px; font-weight: 600; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; }
        .table-scroll { max-height: 500px; overflow: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { position: sticky; top: 0; background: #fafafa; font-weight: 600; text-align: left; padding: 10px 12px; border-bottom: 2px solid #f0f0f0; white-space: nowrap; cursor: pointer; user-select: none; }
        th:hover { background: #f0f0f0; }
        td { padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }
        tr:hover td { background: #f5f7fa; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 500; }
        .badge-现金牛 { background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
        .badge-成长期 { background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }
        .badge-衰退期 { background: #fff2f0; color: #ff4d4f; border: 1px solid #ffccc7; }
        .badge-预警增长 { background: #f9f0ff; color: #722ed1; border: 1px solid #d3adf7; }
        .badge-隐性衰退 { background: #fff7e6; color: #fa8c16; border: 1px solid #ffd591; }
        .badge-新品观察 { background: #fcffe6; color: #a0d911; border: 1px solid #eaff8f; }
        .badge-夕阳产品 { background: #f5f5f5; color: #8c8c8c; border: 1px solid #d9d9d9; }
        .badge-主动收缩 { background: #fff1f0; color: #cf1322; border: 1px solid #ffa39e; }
        .badge-健康扩张 { background: #e6fffb; color: #13c2c2; border: 1px solid #87e8de; }
        .badge-利润优化 { background: #f0f5ff; color: #2f54eb; border: 1px solid #adc6ff; }
        .badge-清仓/偶发 { background: #fafafa; color: #595959; border: 1px solid #d9d9d9; }
        .risk-high { color: #ff4d4f; font-weight: 600; }
        .risk-medium { color: #fa8c16; font-weight: 600; }
        .risk-low { color: #52c41a; font-weight: 600; }
        .summary-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 500; }
        .summary-维持区 { background: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; }
        .summary-观察区 { background: #fff7e6; color: #d46b08; border: 1px solid #ffd591; }
        .summary-投入区 { background: #e6f7ff; color: #096dd9; border: 1px solid #91d5ff; }
        .summary-退出区 { background: #fff2f0; color: #cf1322; border: 1px solid #ffccc7; }
        .summary-待观察 { background: #f5f5f5; color: #595959; border: 1px solid #d9d9d9; }
    </style>
</head>
<body>
    <div class="header">
        <h1>产品生命周期评估看板</h1>
        <div class="meta" id="headerMeta">数据加载中...</div>
    </div>

    <div class="kpi-row" id="kpiRow">
        <div class="kpi-card"><div class="label">产品总数</div><div class="value" id="kpiTotal">-</div><div class="sub">覆盖产品数</div></div>
        <div class="kpi-card"><div class="label">平均毛利率</div><div class="value" id="kpiMargin">-</div><div class="sub">当前毛利率</div></div>
        <div class="kpi-card"><div class="label">平均增长率</div><div class="value" id="kpiGrowth">-</div><div class="sub">近12月增长率</div></div>
        <div class="kpi-card"><div class="label">高风险产品</div><div class="value" id="kpiRisk" style="color:#ff4d4f">-</div><div class="sub">衰退风险等级</div></div>
        <div class="kpi-card"><div class="label">现金牛产品</div><div class="value" id="kpiCash" style="color:#52c41a">-</div><div class="sub">当前画像分布</div></div>
    </div>

    <div class="filters" id="filters">
        <label>筛选：</label>
        <select id="filterPortrait"><option value="">全部画像</option></select>
        <select id="filterSummary"><option value="">全部摘要</option></select>
        <select id="filterRisk"><option value="">全部风险</option></select>
        <select id="filterGroup"><option value="">全部参照组</option></select>
        <select id="filterEnergy"><option value="">全部动能</option></select>
        <button onclick="resetFilters()" style="padding:6px 16px;border:1px solid #d9d9d9;border-radius:4px;background:white;cursor:pointer;font-size:13px;">重置</button>
        <span id="filterCount" style="font-size:13px;color:#8c8c8c;"></span>
    </div>

    <div class="charts-grid">
        <div class="chart-box full">
            <h3>多维气泡图 - 产品画像分布（气泡颜色=画像 | 气泡大小=销量 | X轴=增长率 | Y轴=毛利率 | 点击气泡可联动筛选）</h3>
            <div id="bubbleChart" class="chart" style="height:500px;"></div>
        </div>
        <div class="chart-box">
            <h3>毛利率分布与对比</h3>
            <div id="marginChart" class="chart"></div>
        </div>
        <div class="chart-box">
            <h3>增长率分布</h3>
            <div id="growthChart" class="chart"></div>
        </div>
        <div class="chart-box">
            <h3>画像分布占比</h3>
            <div id="portraitChart" class="chart"></div>
        </div>
        <div class="chart-box">
            <h3>衰退风险等级分布</h3>
            <div id="riskChart" class="chart"></div>
        </div>
    </div>

    <div class="table-section">
        <div class="table-box">
            <h3>
                <span>产品明细列表（点击列标题可排序）</span>
                <span style="font-size:13px;font-weight:normal;color:#8c8c8c;" id="tableCount"></span>
            </h3>
            <div class="table-scroll">
                <table id="detailTable">
                    <thead>
                        <tr>
                            <th data-col="产品名称">产品名称</th><th data-col="所属参照组">所属参照组</th><th data-col="当前画像">当前画像</th><th data-col="管理层摘要">管理层摘要</th>
                            <th data-col="增长率%">增长率%</th><th data-col="当前毛利率%">当前毛利率%</th><th data-col="毛利率同比变化%">毛利率同比变化%</th>
                            <th data-col="近12月销量">近12月销量</th><th data-col="衰退风险得分">衰退风险得分</th><th data-col="衰退风险等级">衰退风险等级</th>
                            <th data-col="风险主导因子">风险主导因子</th><th>通用策略建议</th>
                        </tr>
                    </thead>
                    <tbody id="tableBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        var rawData = ''' + data_str + ''';
        var filteredData = [];
        var chartInstances = {};
        var sortState = { col: null, asc: true };

        var portraitColors = {
            "现金牛": "#52c41a", "成长期": "#1890ff", "衰退期": "#ff4d4f",
            "预警增长": "#722ed1", "隐性衰退": "#fa8c16", "新品观察": "#a0d911",
            "夕阳产品": "#8c8c8c", "主动收缩": "#cf1322", "健康扩张": "#13c2c2",
            "利润优化": "#2f54eb", "清仓/偶发": "#595959"
        };

        var summaryColors = {
            "维持区": "#52c41a", "观察区": "#fa8c16", "投入区": "#1890ff", "退出区": "#ff4d4f", "待观察": "#8c8c8c"
        };

        document.addEventListener("DOMContentLoaded", function() {
            populateFilters();
            applyFilters();
            document.getElementById("headerMeta").textContent = "数据月份：" + rawData[0].最新数据月份 + " | 共 " + rawData.length + " 个产品";
            initSortHandlers();
        });

        function getChart(name) {
            if (chartInstances[name]) {
                chartInstances[name].dispose();
            }
            chartInstances[name] = echarts.init(document.getElementById(name + "Chart"));
            return chartInstances[name];
        }

        function populateFilters() {
            var fields = [
                { id: "filterPortrait", key: "当前画像" },
                { id: "filterSummary", key: "管理层摘要" },
                { id: "filterRisk", key: "衰退风险等级" },
                { id: "filterGroup", key: "所属参照组" },
                { id: "filterEnergy", key: "销量动能" }
            ];
            fields.forEach(function(f) {
                var sel = document.getElementById(f.id);
                var vals = [];
                var seen = {};
                rawData.forEach(function(d) {
                    var v = d[f.key];
                    if (v && !seen[v]) { seen[v] = true; vals.push(v); }
                });
                vals.sort();
                vals.forEach(function(v) {
                    var opt = document.createElement("option");
                    opt.value = v; opt.textContent = v;
                    sel.appendChild(opt);
                });
            });
        }

        function applyFilters() {
            var portrait = document.getElementById("filterPortrait").value;
            var summary = document.getElementById("filterSummary").value;
            var risk = document.getElementById("filterRisk").value;
            var group = document.getElementById("filterGroup").value;
            var energy = document.getElementById("filterEnergy").value;

            filteredData = rawData.filter(function(d) {
                if (portrait && d["当前画像"] !== portrait) return false;
                if (summary && d["管理层摘要"] !== summary) return false;
                if (risk && d["衰退风险等级"] !== risk) return false;
                if (group && d["所属参照组"] !== group) return false;
                if (energy && d["销量动能"] !== energy) return false;
                return true;
            });

            sortState = { col: null, asc: true };
            updateKPIs();
            renderBubbleChart();
            renderMarginChart();
            renderGrowthChart();
            renderPortraitChart();
            renderRiskChart();
            renderTable();
        }

        function updateKPIs() {
            var d = filteredData;
            document.getElementById("kpiTotal").textContent = d.length;
            var margins = d.map(function(x) { return x["当前毛利率%"]; }).filter(function(v) { return v != null; });
            var avgMargin = margins.length ? (margins.reduce(function(a,b) { return a+b; }, 0) / margins.length).toFixed(1) : "-";
            document.getElementById("kpiMargin").textContent = avgMargin !== "-" ? avgMargin + "%" : "-";
            var growths = d.map(function(x) { return x["增长率%"]; }).filter(function(v) { return v != null; });
            var avgGrowth = growths.length ? (growths.reduce(function(a,b) { return a+b; }, 0) / growths.length).toFixed(1) : "-";
            document.getElementById("kpiGrowth").textContent = avgGrowth !== "-" ? avgGrowth + "%" : "-";
            var highRisk = d.filter(function(x) { return x["衰退风险等级"] === "高风险"; }).length;
            document.getElementById("kpiRisk").textContent = highRisk;
            var cash = d.filter(function(x) { return x["当前画像"] === "现金牛"; }).length;
            document.getElementById("kpiCash").textContent = cash;
            document.getElementById("filterCount").textContent = "显示 " + d.length + " / " + rawData.length + " 个产品";
        }

        function resetFilters() {
            document.getElementById("filterPortrait").value = "";
            document.getElementById("filterSummary").value = "";
            document.getElementById("filterRisk").value = "";
            document.getElementById("filterGroup").value = "";
            document.getElementById("filterEnergy").value = "";
            applyFilters();
        }

        function renderBubbleChart() {
            var chart = getChart("bubble");
            var validData = filteredData.filter(function(d) {
                return d["增长率%"] != null && d["当前毛利率%"] != null && d["近12月销量"] != null;
            });

            var seriesData = validData.map(function(d) {
                return {
                    value: [d["增长率%"], d["当前毛利率%"], d["近12月销量"], d["衰退风险得分"] || 0],
                    name: d["产品名称"],
                    itemStyle: { color: portraitColors[d["当前画像"]] || "#ccc" },
                    portrait: d["当前画像"],
                    summary: d["管理层摘要"],
                    energy: d["销量动能"]
                };
            });

            var portraitNames = Object.keys(portraitColors);
            var portraitLegendData = portraitNames.filter(function(p) {
                return validData.some(function(d) { return d["当前画像"] === p; });
            });

            chart.setOption({
                tooltip: {
                    trigger: "item",
                    formatter: function(p) {
                        var d = p.data;
                        var sales = d.value[2] ? d.value[2].toLocaleString() : "-";
                        return "<b>" + d.name + "</b><br/>"
                            + '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + (portraitColors[d.portrait]||"#ccc") + ';margin-right:4px;"></span>画像：' + d.portrait + "<br/>"
                            + '管理层摘要：' + d.summary + "<br/>"
                            + '销量动能：' + d.energy + "<br/>"
                            + '增长率：' + d.value[0] + "%<br/>"
                            + '毛利率：' + d.value[1] + "%<br/>"
                            + '近12月销量：' + sales + "<br/>"
                            + '风险得分：' + d.value[3];
                    }
                },
                legend: {
                    top: 0,
                    data: portraitLegendData,
                    selectedMode: true
                },
                grid: { left: 70, right: 40, bottom: 50, top: 50 },
                xAxis: {
                    name: "增长率 (%)",
                    nameLocation: "middle",
                    nameGap: 30,
                    type: "value",
                    splitLine: { lineStyle: { type: "dashed" } },
                    axisLabel: { formatter: "{value}%" }
                },
                yAxis: {
                    name: "当前毛利率 (%)",
                    type: "value",
                    splitLine: { lineStyle: { type: "dashed" } },
                    axisLabel: { formatter: "{value}%" }
                },
                series: [{
                    type: "scatter",
                    data: seriesData,
                    symbolSize: function(d) {
                        return Math.max(8, Math.min(55, Math.log(d[2] + 1) * 5));
                    },
                    emphasis: {
                        focus: "self",
                        label: { show: true, formatter: function(p) { return p.data.name; }, fontSize: 10, position: "top" }
                    },
                    itemStyle: { opacity: 0.8, borderWidth: 2, borderColor: "#fff" }
                }],
                visualMap: {
                    type: "piecewise",
                    categories: portraitLegendData,
                    inRange: { color: portraitLegendData.map(function(p) { return portraitColors[p]; }) },
                    orient: "horizontal",
                    bottom: 10,
                    left: "center",
                    show: true
                }
            });

            chart.off("click");
            chart.on("click", function(params) {
                if (params.data && params.data.portrait) {
                    document.getElementById("filterPortrait").value = params.data.portrait;
                    applyFilters();
                }
            });
        }

        function renderMarginChart() {
            var chart = getChart("margin");
            var groups = {};
            filteredData.forEach(function(d) {
                if (d["当前毛利率%"] != null) {
                    var g = d["所属参照组"] || "其他";
                    if (!groups[g]) groups[g] = [];
                    groups[g].push(d["当前毛利率%"]);
                }
            });

            var items = Object.keys(groups).map(function(name) {
                var vals = groups[name];
                var sum = vals.reduce(function(a,b) { return a+b; }, 0);
                return { name: name, avg: (sum / vals.length).toFixed(1), count: vals.length };
            }).filter(function(x) { return x.count >= 5; }).sort(function(a,b) { return b.avg - a.avg; }).slice(0, 15);

            chart.setOption({
                tooltip: {
                    formatter: function(p) {
                        var item = items.find(function(x) { return x.name === p.name; });
                        return p.name + "<br/>平均毛利率：" + p.value + "%<br/>产品数：" + (item ? item.count : "-");
                    }
                },
                grid: { left: 120, right: 50, bottom: 40, top: 20 },
                xAxis: { type: "value", name: "毛利率(%)", axisLabel: { formatter: "{value}%" } },
                yAxis: { type: "category", data: items.map(function(x) { return x.name; }).reverse(), axisLabel: { fontSize: 11, width: 100, overflow: "truncate" } },
                series: [{
                    type: "bar",
                    data: items.map(function(x) { return parseFloat(x.avg); }).reverse(),
                    itemStyle: {
                        color: function(params) {
                            return params.value > 30 ? "#52c41a" : params.value > 20 ? "#1890ff" : "#fa8c16";
                        }
                    },
                    label: { show: true, position: "right", formatter: "{c}%", fontSize: 11 }
                }]
            });
        }

        function renderGrowthChart() {
            var chart = getChart("growth");
            var portraitMap = {};
            filteredData.forEach(function(d) {
                if (d["当前画像"] && d["增长率%"] != null) {
                    if (!portraitMap[d["当前画像"]]) portraitMap[d["当前画像"]] = [];
                    portraitMap[d["当前画像"]].push(d["增长率%"]);
                }
            });

            var data = Object.keys(portraitMap).map(function(p) {
                var vals = portraitMap[p];
                var sum = vals.reduce(function(a,b) { return a+b; }, 0);
                return { name: p, avg: (sum / vals.length).toFixed(1), count: vals.length };
            }).sort(function(a,b) { return b.avg - a.avg; });

            chart.setOption({
                tooltip: {
                    formatter: function(p) {
                        var item = data.find(function(x) { return x.name === p.name; });
                        return p.name + "<br/>平均增长率：" + p.value + "%<br/>产品数：" + (item ? item.count : "-");
                    }
                },
                grid: { left: 40, right: 40, bottom: 80, top: 20 },
                xAxis: { type: "category", data: data.map(function(x) { return x.name; }), axisLabel: { fontSize: 11, rotate: 30 } },
                yAxis: { type: "value", name: "平均增长率(%)", axisLabel: { formatter: "{value}%" } },
                series: [{
                    type: "bar",
                    data: data.map(function(x) {
                        return { value: parseFloat(x.avg), itemStyle: { color: portraitColors[x.name] || "#ccc" } };
                    }),
                    label: { show: true, position: "top", formatter: "{c}%", fontSize: 11 }
                }]
            });

            chart.off("click");
            chart.on("click", function(params) {
                if (params.name && portraitColors[params.name] !== undefined) {
                    document.getElementById("filterPortrait").value = params.name;
                    applyFilters();
                }
            });
        }

        function renderPortraitChart() {
            var chart = getChart("portrait");
            var counts = {};
            filteredData.forEach(function(d) {
                if (d["当前画像"]) counts[d["当前画像"]] = (counts[d["当前画像"]] || 0) + 1;
            });
            var data = Object.keys(counts).map(function(name) {
                return { name: name, value: counts[name], itemStyle: { color: portraitColors[name] || "#ccc" } };
            }).sort(function(a,b) { return b.value - a.value; });

            chart.setOption({
                tooltip: {
                    formatter: function(p) {
                        return p.name + "：" + p.value + "个 (" + ((p.value / filteredData.length)*100).toFixed(1) + "%)";
                    }
                },
                series: [{
                    type: "pie",
                    radius: ["40%", "70%"],
                    avoidLabelOverlap: true,
                    label: { formatter: "{b}\\n{d}%", fontSize: 11 },
                    data: data
                }]
            });

            chart.off("click");
            chart.on("click", function(params) {
                if (params.name && portraitColors[params.name] !== undefined) {
                    document.getElementById("filterPortrait").value = params.name;
                    applyFilters();
                }
            });
        }

        function renderRiskChart() {
            var chart = getChart("risk");
            var counts = {};
            filteredData.forEach(function(d) {
                if (d["衰退风险等级"]) counts[d["衰退风险等级"]] = (counts[d["衰退风险等级"]] || 0) + 1;
            });
            var riskColors = { "高风险": "#ff4d4f", "中风险": "#fa8c16", "低风险": "#52c41a", "暂无评分": "#d9d9d9" };
            var data = Object.keys(counts).map(function(name) {
                return { name: name, value: counts[name], itemStyle: { color: riskColors[name] || "#ccc" } };
            });

            chart.setOption({
                tooltip: {
                    formatter: function(p) {
                        return p.name + "：" + p.value + "个 (" + ((p.value / filteredData.length)*100).toFixed(1) + "%)";
                    }
                },
                series: [{
                    type: "pie",
                    radius: ["40%", "70%"],
                    avoidLabelOverlap: true,
                    label: { formatter: "{b}\\n{d}%", fontSize: 11 },
                    data: data
                }]
            });

            chart.off("click");
            chart.on("click", function(params) {
                if (params.name && riskColors[params.name]) {
                    document.getElementById("filterRisk").value = params.name;
                    applyFilters();
                }
            });
        }

        function renderTable() {
            var tbody = document.getElementById("tableBody");
            var display = filteredData.slice();

            if (sortState.col) {
                var col = sortState.col;
                var asc = sortState.asc;
                display.sort(function(a, b) {
                    var va = a[col], vb = b[col];
                    if (va == null) return 1;
                    if (vb == null) return -1;
                    if (typeof va === "number" && typeof vb === "number") {
                        return asc ? va - vb : vb - va;
                    }
                    return asc ? String(va).localeCompare(String(vb), "zh") : String(vb).localeCompare(String(va), "zh");
                });
            }

            display = display.slice(0, 200);
            tbody.innerHTML = display.map(function(d) {
                return "<tr>"
                    + "<td>" + (d["产品名称"] || "-") + "</td>"
                    + "<td>" + (d["所属参照组"] || "-") + "</td>"
                    + '<td><span class="badge badge-' + (d["当前画像"] || "") + '">' + (d["当前画像"] || "-") + "</span></td>"
                    + '<td><span class="summary-badge summary-' + (d["管理层摘要"] || "") + '">' + (d["管理层摘要"] || "-") + "</span></td>"
                    + '<td style="color:' + ((d["增长率%"]||0) >= 0 ? "#52c41a" : "#ff4d4f") + '">' + (d["增长率%"] != null ? d["增长率%"].toFixed(1) : "-") + "</td>"
                    + "<td>" + (d["当前毛利率%"] != null ? d["当前毛利率%"].toFixed(1) : "-") + "</td>"
                    + '<td style="color:' + ((d["毛利率同比变化%"]||0) >= 0 ? "#52c41a" : "#ff4d4f") + '">' + (d["毛利率同比变化%"] != null ? d["毛利率同比变化%"].toFixed(2) : "-") + "</td>"
                    + "<td>" + (d["近12月销量"] != null ? d["近12月销量"].toLocaleString() : "-") + "</td>"
                    + "<td>" + (d["衰退风险得分"] != null ? d["衰退风险得分"].toFixed(1) : "-") + "</td>"
                    + '<td class="' + (d["衰退风险等级"] === "高风险" ? "risk-high" : d["衰退风险等级"] === "中风险" ? "risk-medium" : d["衰退风险等级"] === "低风险" ? "risk-low" : "") + '">' + (d["衰退风险等级"] || "-") + "</td>"
                    + "<td>" + (d["风险主导因子"] || "-") + "</td>"
                    + '<td style="max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + (d["通用策略建议"] || "") + '">' + (d["通用策略建议"] || "-") + "</td>"
                + "</tr>";
            }).join("");
            document.getElementById("tableCount").textContent = "共 " + filteredData.length + " 条，显示前 " + display.length + " 条";
        }

        function initSortHandlers() {
            document.querySelectorAll("#detailTable th[data-col]").forEach(function(th) {
                th.addEventListener("click", function() {
                    var col = th.getAttribute("data-col");
                    if (sortState.col === col) {
                        sortState.asc = !sortState.asc;
                    } else {
                        sortState.col = col;
                        sortState.asc = true;
                    }
                    renderTable();
                });
            });
        }

        document.getElementById("filterPortrait").addEventListener("change", applyFilters);
        document.getElementById("filterSummary").addEventListener("change", applyFilters);
        document.getElementById("filterRisk").addEventListener("change", applyFilters);
        document.getElementById("filterGroup").addEventListener("change", applyFilters);
        document.getElementById("filterEnergy").addEventListener("change", applyFilters);

        window.addEventListener("resize", function() {
            Object.keys(chartInstances).forEach(function(name) {
                if (chartInstances[name]) chartInstances[name].resize();
            });
        });
    </script>
</body>
</html>'''

with open(r'E:\3-其他资料\产品生命周期评估\dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Done! HTML rebuilt with fixed bubble chart and filter linkage.')
