"""一键运行：客户分析"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from customer_analysis.run_pipeline import run
run()
