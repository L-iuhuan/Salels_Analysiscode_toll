"""
预测函数 — 从v2.8提取的ETS预测和加权移动平均。

可被产品生命周期和客户分析复用。
"""

import warnings
import numpy as np
import pandas as pd

try:
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

try:
    import chinese_calendar
    HAS_CHINESE_CALENDAR = True
except ImportError:
    HAS_CHINESE_CALENDAR = False


# [批次⑥ P5] 月度工作日比率缓存：本函数是纯函数（同年月→同结果），但全管道被调用 1400+ 次
# （每个预测实体一次），逐日 is_workday 重复计算同一批月份。按 (year, month) 记忆化，
# 返回值与原计算完全一致，实测可省 ~15-19s。
_WORKDAY_RATIO_CACHE = {}


def calc_monthly_holiday_ratios(year_months):
    """基于chinese_calendar计算每月实际工作日占比。

    参数:
        year_months: Period对象列表

    返回:
        dict: {Period: 工作日比率}
    """
    if not HAS_CHINESE_CALENDAR:
        return {pm: 1.0 for pm in year_months}

    ratios = {}
    for pm in year_months:
        year = pm.year
        month = pm.month
        key = (year, month)
        cached = _WORKDAY_RATIO_CACHE.get(key)
        if cached is not None:
            ratios[pm] = cached
            continue
        total_days = pd.Timestamp(year, month, 1).days_in_month
        workdays = 0
        for day in range(1, total_days + 1):
            dt = pd.Timestamp(year, month, day)
            if chinese_calendar.is_workday(dt):
                workdays += 1
        ratio = workdays / 22.0
        _WORKDAY_RATIO_CACHE[key] = ratio
        ratios[pm] = ratio
    return ratios


def prepare_holiday_adjustment(monthly_qty, all_periods, pred_periods, thr=None):
    """节假日调整系数计算。
    
    参数:
        monthly_qty: 月度销量序列
        all_periods: 历史月份Period列表
        pred_periods: 预测月份Period列表
        thr: 阈值字典
    
    返回:
        list: 每个预测月份的调整系数
    """
    enable = 1
    if thr:
        enable = thr.get("forecast_holiday_adjust", 1)
    
    if enable != 1 or not HAS_CHINESE_CALENDAR:
        return [1.0] * len(pred_periods)
    
    hist_ratios = calc_monthly_holiday_ratios(all_periods)
    pred_ratios = calc_monthly_holiday_ratios(pred_periods)
    
    adjustments = []
    for pred_p in pred_periods:
        pred_r = pred_ratios.get(pred_p, 1.0)
        hist_months = [p for p in all_periods if p.month == pred_p.month]
        if hist_months:
            hist_r = np.mean([hist_ratios.get(m, 1.0) for m in hist_months])
        else:
            hist_r = 1.0
        adj = pred_r / hist_r if hist_r > 0 else 1.0
        adj = max(0.5, min(1.2, adj))
        adjustments.append(adj)
    
    return adjustments


def ets_forecast(monthly_qty, periods=3, seasonal_periods=0):
    """ETS状态空间模型预测。
    
    参数:
        monthly_qty: 月度销量序列
        periods: 预测月数
        seasonal_periods: 季节性周期长度，0=自动检测
    
    返回:
        tuple: (forecast, direction, pred_intervals, model_info)
    """
    if not HAS_STATSMODELS:
        return None, "statsmodels未安装", None, None
    
    if len(monthly_qty) < 4:
        return None, "数据不足", None, None
    
    # statsmodels ETS 拟合/预测在稀疏数据上产生数值警告，属于算法特性
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _ets_forecast_impl(monthly_qty, periods, seasonal_periods)


def _ets_forecast_impl(monthly_qty, periods=3, seasonal_periods=0):
    """ETS 预测内部实现，调用方应在外层 suppress statsmodels 警告。"""
    y = np.asarray(monthly_qty, dtype=float)
    neg_count = int((y < 0).sum())
    if neg_count > 0:
        print(f"  [ETS] 警告: {neg_count}/{len(y)} 个负值被钳制为0")
    y = np.maximum(y, 0)
    
    use_seasonal = seasonal_periods if seasonal_periods and seasonal_periods >= 2 else None
    
    best_aic = np.inf
    best_result = None
    best_model_type = None
    
    n = len(y)
    configs = []
    if n < 12:
        for e in ['add']:
            for t in ['add', None]:
                configs.append((e, t, None))
    elif n < 18:
        configs = [('add', 'add', None), ('add', None, None), ('mul', 'add', None)]
    else:
        for e in ['add', 'mul']:
            for t in ['add', 'mul', None]:
                for s in [None]:
                    configs.append((e, t, s))

    if use_seasonal and n >= 24:
        extra = []
        for e in ['add', 'mul']:
            for t in ['add', None]:
                for s in ['add', 'mul']:
                    extra.append((e, t, s))
        configs = extra + configs

    for err, trend, seas in configs:
        try:
            model = ETSModel(
                y,
                error=err,
                trend=trend,
                seasonal=seas,
                seasonal_periods=use_seasonal,
            )
            fit = model.fit(disp=False)
            if fit.aic < best_aic:
                best_aic = fit.aic
                best_result = (model, fit)
                best_model_type = f"ETS({err},{trend or 'N'},{seas or 'N'})"
        except (ValueError, np.linalg.LinAlgError, RuntimeError):
            continue
    
    if best_result is None:
        try:
            model = ETSModel(y, error='add', trend='add', seasonal=None)
            fit = model.fit(disp=False)
            best_result = (model, fit)
            best_model_type = "ETS(A,A,N)"
            best_aic = fit.aic
        except (ValueError, np.linalg.LinAlgError, RuntimeError):
            return None, "建模失败", None, None
    
    model, fit = best_result
    forecast_result = fit.forecast(periods)
    forecast = []
    for v in forecast_result:
        if pd.isna(v) or np.isnan(float(v)):
            forecast.append(0)
        else:
            forecast.append(max(0, int(round(float(v), 0))))
    
    try:
        params_dict = dict(fit.params) if hasattr(fit, 'params') else {}
        trend_val = params_dict.get('smoothing_trend', 0)
    except (KeyError, AttributeError, TypeError):
        trend_val = 0
    
    avg_qty = np.mean(y)
    if len(forecast) > 0 and avg_qty > 0 and abs(forecast[-1] - y[-1]) / avg_qty > 0.05:
        direction = "上升" if forecast[-1] > y[-1] else "下降"
    else:
        direction = "平稳"
    
    pred_intervals = {}
    try:
        pred = fit.get_prediction(start=len(y), end=len(y) + periods - 1)
        for alpha_val, label in [(0.2, 80), (0.05, 95)]:
            try:
                ci = pred.pred_int(alpha=alpha_val)
                lower = [0 if pd.isna(v) else max(0, round(v, 0)) for v in ci.iloc[:, 0]]
                upper = [0 if pd.isna(v) else max(0, round(v, 0)) for v in ci.iloc[:, 1]]
                pred_intervals[label] = (lower, upper)
            except (ValueError, IndexError):
                pred_intervals[label] = (None, None)
    except (ValueError, AttributeError):
        try:
            scale = fit.scale if hasattr(fit, 'scale') and fit.scale > 0 else np.var(y)
            if pd.isna(scale) or np.isinf(scale):
                scale = np.var(y)
            for z_val, label in [(1.28, 80), (1.96, 95)]:
                half = z_val * np.sqrt(scale)
                lower = [0 if pd.isna(f) else max(0, round(f - half, 0)) for f in forecast]
                upper = [0 if pd.isna(f) else max(0, round(f + half, 0)) for f in forecast]
                pred_intervals[label] = (lower, upper)
        except (ValueError, TypeError):
            pred_intervals = {80: (None, None), 95: (None, None)}
    
    model_info = {
        'model_type': best_model_type,
        'aic': round(best_aic, 1) if best_aic != np.inf else None
    }
    return forecast, direction, pred_intervals, model_info


def ets_forecast_picklable(args):
    """[批次⑥ P3] ProcessPool worker：解包参数调用 ets_forecast。

    必须是模块级函数（Windows spawn 下 worker 按导入路径反序列化）。
    结果与串行直接调用 ets_forecast 完全一致（同一确定性算法、同一输入）。
    """
    monthly_qty, periods, seasonal_periods = args
    return ets_forecast(monthly_qty, periods=periods, seasonal_periods=seasonal_periods)


def weighted_ma_forecast(monthly_qty, periods=3, window=3):
    """加权移动平均预测（兜底用）。
    
    参数:
        monthly_qty: 月度销量序列
        periods: 预测月数
        window: 移动平均窗口
    
    返回:
        tuple: (forecast, direction)
    """
    if len(monthly_qty) < window:
        return None, "数据不足"
    
    recent = np.array(monthly_qty[-window:])
    weights = np.arange(1, window + 1)
    weighted_avg = np.sum(recent * weights) / np.sum(weights)
    recent_trend = recent[-1] - recent[-2] if len(recent) >= 2 else 0
    forecast = [max(0, weighted_avg + i * recent_trend * 0.5) for i in range(periods)]
    
    avg_qty = np.mean(monthly_qty)
    if recent_trend > avg_qty * 0.05:
        direction = "上升"
    elif recent_trend < -avg_qty * 0.05:
        direction = "下降"
    else:
        direction = "平稳"
    
    return forecast, direction
