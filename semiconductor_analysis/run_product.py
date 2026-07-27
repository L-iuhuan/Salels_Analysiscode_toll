"""一键运行：产品生命周期分析"""
import warnings
import sys, os

# 抑制已知的良性警告（第三方库 / pandas 版本迁移）
warnings.filterwarnings("ignore", category=FutureWarning, message=".*observed=False.*")
warnings.filterwarnings("ignore", category=FutureWarning, message=".*Downcasting object dtype.*")
warnings.filterwarnings("ignore", message=".*Maximum Likelihood optimization failed.*")
warnings.filterwarnings("ignore", message=".*divide by zero.*")
warnings.filterwarnings("ignore", message=".*invalid value encountered.*")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from product_lifecycle.run import run
if __name__ == '__main__':
    run(skip_silver=True)
