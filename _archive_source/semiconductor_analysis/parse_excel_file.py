#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel文件解析脚本
用于解析并展示Chart_Data_Q13_Forecast_Update_v2.0_20260610.xlsx文件的结构和内容
"""

import pandas as pd
import sys
import os

def analyze_excel_file(file_path):
    """分析Excel文件的所有工作表和数据结构"""
    try:
        # 获取所有工作表名称
        excel_file = pd.ExcelFile(file_path)
        sheet_names = excel_file.sheet_names
        
        print(f"Excel文件路径: {file_path}")
        print("="*80)
        print(f"工作表列表 (共{len(sheet_names)}个):")
        for i, sheet in enumerate(sheet_names, 1):
            print(f"{i}. {sheet}")
        
        print("\n" + "="*80)
        
        # 逐个分析每个工作表
        for sheet_name in sheet_names:
            print(f"\n工作表: {sheet_name}")
            print("-" * 50)
            
            try:
                # 读取工作表数据
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                
                # 显示基本信息
                print(f"行数: {len(df)}")
                print(f"列数: {len(df.columns)}")
                
                # 显示列名
                print("\n列名:")
                for i, col in enumerate(df.columns, 1):
                    print(f"{i}. {col}")
                
                # 显示前几行数据（如果存在数据）
                if len(df) > 0:
                    print("\n前5行数据预览:")
                    print(df.head())
                
                # 检查数据类型
                print("\n数据类型:")
                for col, dtype in df.dtypes.items():
                    print(f"{col}: {dtype}")
                
            except Exception as e:
                print(f"读取工作表 '{sheet_name}' 时出错: {str(e)}")
            
            print("\n" + "="*80)
            
    except Exception as e:
        print(f"分析Excel文件时出错: {str(e)}")

if __name__ == "__main__":
    # 指定要解析的Excel文件路径
    file_path = "quarterly_forecast_package/Chart_Data_Q13_Forecast_Update_v2.0_20260610.xlsx"
    
    if os.path.exists(file_path):
        analyze_excel_file(file_path)
    else:
        print(f"错误: 找不到文件 '{file_path}'")
        print("请确认文件路径是否正确。")