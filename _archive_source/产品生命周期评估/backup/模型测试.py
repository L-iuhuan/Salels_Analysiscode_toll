"""
完整历史数据（5-6年）的模型对比测试 – 针对A类主力SKU
需要安装：pandas, openpyxl, statsmodels, prophet, scikit-learn, matplotlib
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.exponential_smoothing.ets import ETSModel
from statsmodels.tsa.statespace.sarimax import SARIMAX
from prophet import Prophet
from sklearn.metrics import mean_absolute_error

# ========== 用户配置区域 ==========
EXCEL_FILE = r"E:\3-其他资料\产品生命周期评估\所有的出货明细5.7.xlsx"   # 请修改为您2020年至今的完整文件
SHEET_NAME = "所有的出货明细"

# 字段列名（根据您的实际Excel修改）
COL_DATE = "发货日期"
COL_SKU = "存货名称"
COL_QTY = "发货数量"
COL_AMOUNT = "RMB 未税金额小计"

# 测试参数
TRAIN_MONTHS = 48       # 训练月数（建议至少36，有4个季节周期）
TEST_MONTHS = 12        # 测试月数（最后12个月）
TOP_SKU_TEST = 20       # 测试前20个A类SKU（按总金额）
CROSS_VALIDATION_WINDOWS = 2   # 滚动窗口数（例如第1窗口：前48月→后12月；第2窗口：前36月→最后12月）

# 是否使用金额（True）或数量（False）作为预测目标
USE_AMOUNT = True

# ========== 以下代码无需修改 ==========

def sMAPE(y_true, y_pred):
    """对称平均绝对百分比误差（%），处理零值"""
    return 100 * np.mean(2 * np.abs(y_true - y_pred) / (np.abs(y_true) + np.abs(y_pred) + 1e-6))

def evaluate_model(y_true, y_pred, model_name):
    """计算sMAPE和MAE"""
    smape = sMAPE(y_true, y_pred)
    mae = mean_absolute_error(y_true, y_pred)
    return {'model': model_name, 'sMAPE': smape, 'MAE': mae}

# 1. 读取数据
df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
print(f"原始订单行数：{len(df)}")
df.rename(columns={COL_DATE: 'date', COL_SKU: 'sku', COL_QTY: 'qty', COL_AMOUNT: 'amount'}, inplace=True)
df['date'] = pd.to_datetime(df['date'])
df = df[(df['qty'] >= 0) & (df['amount'] >= 0)]

# 按月聚合
df['year_month'] = df['date'].dt.to_period('M')
monthly = df.groupby(['sku', 'year_month']).agg({'qty': 'sum', 'amount': 'sum'}).reset_index()

# 获取完整月份序列
all_months = pd.period_range(start=monthly['year_month'].min(), end=monthly['year_month'].max(), freq='M')
skus = monthly['sku'].unique()
print(f"共有 {len(skus)} 个SKU")

# 构建每个SKU的月度序列（金额或数量）
target_col = 'amount' if USE_AMOUNT else 'qty'
sku_series = {}
for sku in skus:
    sku_data = monthly[monthly['sku'] == sku].set_index('year_month')
    ts = sku_data[target_col].reindex(all_months, fill_value=0)
    sku_series[sku] = ts

# 2. 筛选A类SKU（按总金额排序）
stats = []
for sku, ts in sku_series.items():
    total = ts.sum()
    non_zero = (ts > 0).sum()
    zero_ratio = 1 - non_zero / len(ts)
    stats.append({'sku': sku, 'total_amount': total, 'zero_ratio': zero_ratio})
stats_df = pd.DataFrame(stats).sort_values('total_amount', ascending=False)
# 简单规则：总金额高且零比例<30%视为A类
a_skus = stats_df[(stats_df['total_amount'] > stats_df['total_amount'].quantile(0.8)) & (stats_df['zero_ratio'] < 0.3)]['sku'].head(TOP_SKU_TEST).tolist()
print(f"\n测试的A类SKU: {a_skus}")

# 3. 定义模型预测函数
def naive_seasonal(train, test_len, period=12):
    """季节性Naive：用最后一个周期的值"""
    last_cycle = train.iloc[-period:] if len(train) >= period else train
    pred = np.tile(last_cycle.values, int(np.ceil(test_len / period)))[:test_len]
    return pred

def holt_winters(train, test_len, seasonal_periods=12):
    try:
        model = ExponentialSmoothing(train, seasonal_periods=seasonal_periods, trend='add', seasonal='add', initialization_method='estimated').fit()
        return model.forecast(test_len)
    except:
        return np.full(test_len, np.nan)

def ets_model(train, test_len):
    try:
        model = ETSModel(train, error='add', trend='add', seasonal='add', seasonal_periods=12).fit()
        return model.forecast(test_len)
    except:
        return np.full(test_len, np.nan)

def sarima_model(train, test_len):
    try:
        # 简单自动参数：使用AIC搜索，但为速度先固定常用阶数
        model = SARIMAX(train, order=(1,1,1), seasonal_order=(1,1,1,12), enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
        return model.forecast(test_len)
    except:
        return np.full(test_len, np.nan)

def prophet_model(train_dates, train_vals, test_len, freq='MS'):
    """train_dates: pandas DatetimeIndex, train_vals: series values"""
    df_prophet = pd.DataFrame({'ds': train_dates.to_timestamp(), 'y': train_vals})
    # 添加中国节假日（需要先安装holidays包，或手动列出）
    model = Prophet(seasonality_mode='additive', yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
    model.add_country_holidays(country_name='CN')
    model.fit(df_prophet)
    future = model.make_future_dataframe(periods=test_len, freq=freq, include_history=False)
    forecast = model.predict(future)
    return forecast['yhat'].values

# 4. 滚动交叉验证
results = []
for sku in a_skus:
    ts = sku_series[sku]
    if len(ts) < TRAIN_MONTHS + TEST_MONTHS:
        print(f"SKU {sku} 历史长度不足 {TRAIN_MONTHS+TEST_MONTHS} 个月，跳过")
        continue
    
    # 生成多个训练/测试划分（从后往前滚动）
    splits = []
    for i in range(CROSS_VALIDATION_WINDOWS):
        train_end = -TEST_MONTHS - i * TEST_MONTHS
        if train_end <= TRAIN_MONTHS:
            train = ts[:train_end]
            test = ts[train_end:train_end+TEST_MONTHS]
            if len(test) == TEST_MONTHS:
                splits.append((train, test))
    
    if not splits:
        print(f"SKU {sku} 无法生成有效交叉验证窗口")
        continue
    
    per_sku_results = []
    for train, test in splits:
        # 确保test索引正确
        y_true = test.values
        # 1. Naive
        naive_pred = naive_seasonal(train, len(test))
        # 2. Holt-Winters
        hw_pred = holt_winters(train, len(test))
        # 3. ETS
        ets_pred = ets_model(train, len(test))
        # 4. SARIMA
        sarima_pred = sarima_model(train, len(test))
        # 5. Prophet (需要日期索引)
        # 如果训练期少于2个季节周期，跳过Prophet
        if len(train) >= 24:
            prophet_pred = prophet_model(train.index, train.values, len(test))
        else:
            prophet_pred = np.full(len(test), np.nan)
        
        # 收集误差
        metrics = {}
        metrics['naive'] = evaluate_model(y_true, naive_pred, 'naive')
        if not np.isnan(hw_pred).any():
            metrics['hw'] = evaluate_model(y_true, hw_pred, 'hw')
        if not np.isnan(ets_pred).any():
            metrics['ets'] = evaluate_model(y_true, ets_pred, 'ets')
        if not np.isnan(sarima_pred).any():
            metrics['sarima'] = evaluate_model(y_true, sarima_pred, 'sarima')
        if not np.isnan(prophet_pred).any():
            metrics['prophet'] = evaluate_model(y_true, prophet_pred, 'prophet')
        
        per_sku_results.append(metrics)
    
    # 对多个窗口取平均sMAPE
    avg_metrics = {}
    for model_name in ['naive', 'hw', 'ets', 'sarima', 'prophet']:
        smape_list = []
        for window in per_sku_results:
            if model_name in window:
                smape_list.append(window[model_name]['sMAPE'])
        if smape_list:
            avg_metrics[model_name] = np.mean(smape_list)
    
    # 找出最佳模型
    best_model = min(avg_metrics, key=avg_metrics.get) if avg_metrics else None
    results.append({
        'sku': sku,
        **avg_metrics,
        'best_model': best_model,
        'best_sMAPE': avg_metrics.get(best_model, np.nan)
    })

# 5. 输出结果
results_df = pd.DataFrame(results)
print("\n===== 模型对比结果（平均sMAPE，越低越好）=====")
print(results_df.round(2).to_string(index=False))
results_df.to_excel("full_model_test_results.xlsx", index=False)
print("\n详细结果已保存到 full_model_test_results.xlsx")