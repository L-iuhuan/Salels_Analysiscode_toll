============================================================
产品线季度预测工具包
============================================================

本工具包包含完整的产品线季度预测系统，可直接运行。

目录结构：
------------------------------------------------------------
quarterly_forecast_package/
├── run_quarterly_forecast.py      # 主程序
├── forecast_config.default.json   # 配置文件
├── chart_template.html            # 图表模板
├── chartjs.min.js                 # Chart.js库（离线可用）
├── 产品线季度预测实施方案.md         # 方法设计文档
├── 使用说明.md                     # 完整使用说明
├── README.txt                     # 本文件
└── output/
    └── quarterly_forecast_locked/
        ├── 产品线季度历史与预测.csv          # 最终主表
        ├── 产品线季度历史与预测_含方法回测.xlsx # Excel整合版
        ├── 产品线季度预测图表.html           # 交互式图表（可直接打开）
        ├── 预测方法排行榜.csv                # 方法选择记录
        ├── 预测方法回测明细.csv              # 回测记录（锁定模式为空）
        ├── 产品级价格与预测贡献.csv          # 产品级价格诊断
        ├── 候选预测方法清单.csv              # 所有候选方法
        ├── 数据质量与映射诊断.csv            # 数据质量诊断
        └── 操作日志.csv                      # 运行日志

快速开始：
------------------------------------------------------------
1. 确保安装Python 3.10+和依赖：
   pip install pandas numpy openpyxl python-calamine

2. 将出货明细Excel文件放入data目录（需自行创建）

3. 修改配置文件中的data_path指向你的Excel文件

4. 运行全量回测（首次）：
   python run_quarterly_forecast.py --config forecast_config.default.json

5. 运行锁定模式（后续快速刷新）：
   python run_quarterly_forecast.py --config forecast_config.default.json --method-lock output/quarterly_forecast_locked/预测方法排行榜.csv

6. 直接查看图表：
   打开 output/quarterly_forecast_locked/产品线季度预测图表.html

配置说明：
------------------------------------------------------------
配置文件 forecast_config.default.json 可修改：
- data_path: Excel文件路径
- sheet_name: 工作表名称或序号
- field_map: 字段映射（左侧标准字段，右侧实际字段名）

详细说明请参考：使用说明.md

注意事项：
------------------------------------------------------------
1. 首次运行请使用全量回测模式，约需5-10分钟
2. 后续数据更新可使用锁定模式，约需1-2分钟
3. 图表文件可直接用浏览器打开，无需联网
4. 历史毛利额使用原始利润字段汇总
5. 预测上下限基于历史回测误差生成

版本信息：
------------------------------------------------------------
生成日期：2026-06-10
数据截止：2026-04
历史期数：12期（每期3个月）
预测期数：4期
