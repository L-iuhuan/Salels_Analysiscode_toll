#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel文件详细分析脚本
对Chart_Data_Q13_Forecast_Update_v2.0_20260610.xlsx进行更深入的分析
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

def analyze_chart_data_sheet(file_path):
    """分析图表数据工作表"""
    print("\n【图表数据工作表详细分析】")
    print("="*80)
    
    # 读取工作表
    df = pd.read_excel(file_path, sheet_name="图表数据", header=None)
    
    # 提取标题行
    title = df.iloc[0, 0]
    print(f"标题: {title}")
    
    # 提取季度列（假设在第2行）
    quarters = df.iloc[1, 2:].values
    print(f"\n季度范围: {len(quarters)}个季度")
    print("季度列表:")
    for i, q in enumerate(quarters):
        if not pd.isna(q):
            print(f"  {i+1}. {q}")
    
    # 提取产品线数据
    product_lines = df.iloc[2:, 0].dropna().values
    print(f"\n产品线数量: {len(product_lines)}")
    print("产品线列表:")
    for i, line in enumerate(product_lines):
        print(f"  {i+1}. {line}")
    
    # 获取销量数据（跳过前两行和第一列）
    sales_data = df.iloc[2:, 2:].values
    
    # 尝试统计数据总和（仅对数值数据进行）
    try:
        # 创建一个只包含数值的数组
        numeric_data = np.array([])
        for col in sales_data.T:
            # 尝试将每列转换为数值
            try:
                numeric_col = pd.to_numeric(col, errors='coerce')
                if len(numeric_data) == 0:
                    numeric_data = numeric_col.reshape(-1, 1)
                else:
                    numeric_data = np.hstack((numeric_data, numeric_col.reshape(-1, 1)))
            except:
                pass  # 跳过无法转换为数值的列
        
        if len(numeric_data) > 0:
            total_sales_by_quarter = np.nansum(numeric_data, axis=0)
            print(f"\n各季度销售总量（仅统计数值数据）:")
            for i, total in enumerate(total_sales_by_quarter):
                if i < len(quarters) and not pd.isna(quarters[i]) and not pd.isna(total):
                    print(f"  {quarters[i]}: {int(total):,}")
    except Exception as e:
        print(f"\n统计销量数据时出错: {str(e)}")
    
    return df, product_lines, quarters, sales_data

def analyze_volume_price_params(file_path):
    """分析量价参数工作表"""
    print("\n【量价参数工作表详细分析】")
    print("="*80)
    
    # 读取工作表（第一行是标题）
    df = pd.read_excel(file_path, sheet_name="量价参数")
    
    print(f"数据行数: {len(df)}")
    print(f"数据列数: {len(df.columns)}")
    
    # 显示列名
    print("\n列名:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col}")
    
    # 分析预测方法分布
    method_counts = df['选用方法'].value_counts()
    print("\n预测方法分布:")
    for method, count in method_counts.items():
        print(f"  {method}: {count}个产品线")
    
    # 分析销量回测WAPE (Weighted Absolute Percentage Error)
    wape_stats = df['销量回测WAPE'].describe()
    print("\nWAPE (Weighted Absolute Percentage Error) 统计:")
    print(f"  平均值: {wape_stats['mean']:.4f}")
    print(f"  中位数: {wape_stats['50%']:.4f}")
    print(f"  最小值: {wape_stats['min']:.4f}")
    print(f"  最大值: {wape_stats['max']:.4f}")
    print(f"  标准差: {wape_stats['std']:.4f}")
    
    # 显示量价参数详情
    print("\n各产品线预测详情:")
    important_cols = ['产品线', '选用方法', '单价预测(公式)', '单位利润预测(公式)', '销量回测WAPE']
    print(df[important_cols].to_string(index=False))
    
    return df

def analyze_monthly_data(file_path):
    """分析月度底表工作表"""
    print("\n【月度底表工作表详细分析】")
    print("="*80)
    
    # 读取工作表
    df = pd.read_excel(file_path, sheet_name="月度底表")
    
    print(f"数据行数: {len(df)}")
    print(f"数据列数: {len(df.columns)}")
    
    # 显示列名
    print("\n列名:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col}")
    
    # 分析时间范围（跳过非日期格式的行）
    try:
        # 尝试转换日期，只保留可以转换的行
        date_mask = df['月份'].astype(str).str.match(r'^\d{4}-\d{2}$')
        valid_dates_df = df[date_mask].copy()
        
        if len(valid_dates_df) > 0:
            valid_dates_df['月份'] = pd.to_datetime(valid_dates_df['月份'], format='%Y-%m')
            min_date = valid_dates_df['月份'].min()
            max_date = valid_dates_df['月份'].max()
            months_count = len(valid_dates_df['月份'].unique())
            
            print(f"\n时间范围: {min_date.strftime('%Y-%m')} 到 {max_date.strftime('%Y-%m')}")
            print(f"总月份数: {months_count}")
            
            # 使用有效日期的数据进行后续分析
            df = valid_dates_df
        else:
            print("\n警告: 未找到有效的日期格式数据 (YYYY-MM)")
    except Exception as e:
        print(f"\n分析时间范围时出错: {str(e)}")
    
    # 分析产品线分布
    product_lines = df['产品线'].value_counts()
    print(f"\n产品线数量: {len(product_lines)}")
    print("各产品线数据点数量:")
    for line, count in product_lines.items():
        print(f"  {line}: {count}个月数据点")
    
    # 计算总体统计信息
    total_sales = df['销量(颗)'].sum()
    total_revenue = df['收入RMB(M×汇率)'].sum()
    total_profit = df['利润(Q列)'].sum()
    
    print(f"\n总体统计:")
    print(f"  总销量: {total_sales:,.0f} 颗")
    print(f"  总收入: {total_revenue:,.2f} 元")
    print(f"  总利润: {total_profit:,.2f} 元")
    
    # 按年份统计（仅当有有效日期数据时）
    if '月份' in df.columns and pd.api.types.is_datetime64_any_dtype(df['月份']):
        df['年份'] = df['月份'].dt.year
        yearly_stats = df.groupby('年份').agg({
            '销量(颗)': 'sum',
            '收入RMB(M×汇率)': 'sum',
            '利润(Q列)': 'sum'
        })
        
        print(f"\n按年份统计:")
        for year, stats in yearly_stats.iterrows():
            print(f"  {year}年: 销量={stats['销量(颗)']:,.0f} 颗, 收入={stats['收入RMB(M×汇率)']:,.2f} 元, 利润={stats['利润(Q列)']:,.2f} 元")
    else:
        print("\n按年份统计: 无法进行，缺少有效的日期数据")
    
    return df

def analyze_method_notes(file_path):
    """分析方法说明工作表"""
    print("\n【方法说明工作表分析】")
    print("="*80)
    
    # 读取工作表
    df = pd.read_excel(file_path, sheet_name="方法说明", header=None)
    
    print(f"数据行数: {len(df)}")
    print(f"数据列数: {len(df.columns)}")
    
    # 显示内容（如果第一列不为空）
    for i in range(len(df)):
        if not pd.isna(df.iloc[i, 0]):
            print(f"{i+1}. {df.iloc[i, 0]}")
            # 读取该行的其他列内容
            for j in range(1, len(df.columns)):
                if not pd.isna(df.iloc[i, j]):
                    print(f"   {df.iloc[i, j]}")
            print()  # 空行分隔
    
    return df

def main():
    # 指定要解析的Excel文件路径
    file_path = "quarterly_forecast_package/Chart_Data_Q13_Forecast_Update_v2.0_20260610.xlsx"
    
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 '{file_path}'")
        return
    
    print("="*100)
    print("Excel文件详细分析报告")
    print("="*100)
    print(f"文件名: {os.path.basename(file_path)}")
    print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100)
    
    try:
        # 分析各个工作表
        chart_df, product_lines, quarters, sales_data = analyze_chart_data_sheet(file_path)
        volume_price_df = analyze_volume_price_params(file_path)
        monthly_df = analyze_monthly_data(file_path)
        method_df = analyze_method_notes(file_path)
        
        print("\n" + "="*100)
        print("分析完成")
        print("="*100)
        
    except Exception as e:
        print(f"分析过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()