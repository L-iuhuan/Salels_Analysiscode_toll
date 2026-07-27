import time
import random
from collections import defaultdict, Counter


def find_duplicates_original(data):
    """原始版本 - O(n³) 时间复杂度"""
    duplicates = []
    for i in range(len(data)):
        for j in range(i+1, len(data)):
            if data[i] == data[j] and data[i] not in duplicates:
                duplicates.append(data[i])
    return duplicates


def find_duplicates_optimized_v1(data):
    """优化版本1 - 使用set - O(n) 时间复杂度"""
    seen = set()
    duplicates = set()
    
    for item in data:
        if item in seen:
            duplicates.add(item)
        else:
            seen.add(item)
    
    return list(duplicates)


def find_duplicates_optimized_v2(data):
    """优化版本2 - 使用Counter - O(n) 时间复杂度"""
    counter = Counter(data)
    return [item for item, count in counter.items() if count > 1]


def find_duplicates_optimized_v3(data):
    """优化版本3 - 使用defaultdict - O(n) 时间复杂度"""
    counts = defaultdict(int)
    for item in data:
        counts[item] += 1
    
    return [item for item, count in counts.items() if count > 1]


def find_duplicates_optimized_v4(data):
    """优化版本4 - 使用字典推导式 - O(n) 时间复杂度"""
    counts = {}
    for item in data:
        counts[item] = counts.get(item, 0) + 1
    
    return [item for item, count in counts.items() if count > 1]


def generate_test_data(size):
    """生成测试数据"""
    print(f"生成 {size:,} 条测试数据...")
    
    # 生成一个列表，其中约70%是唯一值，30%是重复值
    unique_count = int(size * 0.7)
    duplicate_count = size - unique_count
    
    # 生成唯一值
    unique_items = list(range(unique_count))
    
    # 从唯一值中随机选择一些作为重复值
    duplicate_items = random.choices(unique_items, k=duplicate_count)
    
    # 合并并打乱
    data = unique_items + duplicate_items
    random.shuffle(data)
    
    print(f"数据生成完成，其中 {len(unique_items):,} 个唯一值，{len(duplicate_items):,} 个重复值")
    return data


def test_performance():
    """测试不同版本的性能"""
    # 测试不同规模的数据
    test_sizes = [100, 1000, 10000, 100000]
    
    for size in test_sizes:
        print(f"\n{'='*80}")
        print(f"测试数据规模: {size:,}")
        print(f"{'='*80}")
        
        # 生成测试数据
        data = generate_test_data(size)
        
        # 测试原始版本（仅在小数据集上）
        if size <= 10000:  # 原始版本在大数据上太慢
            print("\n测试原始版本:")
            start_time = time.time()
            result_original = find_duplicates_original(data)
            end_time = time.time()
            original_time = end_time - start_time
            original_count = len(result_original)
            print(f"执行时间: {original_time:.4f} 秒")
            print(f"找到重复元素: {original_count} 个")
        
        # 测试优化版本
        versions = [
            ("优化版本1 (使用set)", find_duplicates_optimized_v1),
            ("优化版本2 (使用Counter)", find_duplicates_optimized_v2),
            ("优化版本3 (使用defaultdict)", find_duplicates_optimized_v3),
            ("优化版本4 (使用字典)", find_duplicates_optimized_v4),
        ]
        
        for version_name, version_func in versions:
            print(f"\n测试{version_name}:")
            start_time = time.time()
            result_optimized = version_func(data)
            end_time = time.time()
            optimized_time = end_time - start_time
            optimized_count = len(result_optimized)
            print(f"执行时间: {optimized_time:.6f} 秒")
            print(f"找到重复元素: {optimized_count} 个")
            
            # 计算性能提升（仅在测试过原始版本时）
            if size <= 10000:
                if optimized_time > 0:
                    speedup = original_time / optimized_time
                    print(f"性能提升: {speedup:.1f}x")
                else:
                    print(f"性能提升: > 1000x (执行时间 < 0.000001秒)")
        
        print(f"\n数据规模 {size:,} 的测试完成")


def test_large_dataset():
    """测试大数据集上的性能"""
    print(f"\n{'='*80}")
    print(f"大数据集测试 (1,000,000 条数据)")
    print(f"{'='*80}")
    
    # 生成大规模测试数据
    data = generate_test_data(1000000)
    
    # 只测试优化版本
    versions = [
        ("优化版本1 (使用set)", find_duplicates_optimized_v1),
        ("优化版本2 (使用Counter)", find_duplicates_optimized_v2),
        ("优化版本3 (使用defaultdict)", find_duplicates_optimized_v3),
        ("优化版本4 (使用字典)", find_duplicates_optimized_v4),
    ]
    
    best_time = float('inf')
    best_version = ""
    
    for version_name, version_func in versions:
        print(f"\n测试{version_name}:")
        start_time = time.time()
        result = version_func(data)
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"执行时间: {execution_time:.6f} 秒")
        print(f"找到重复元素: {len(result)} 个")
        
        if execution_time < best_time:
            best_time = execution_time
            best_version = version_name
    
    print(f"\n最佳性能: {best_version} ({best_time:.6f} 秒)")
    
    # 估算1000万条数据的执行时间
    estimated_time = best_time * 10  # 线性估算
    print(f"预估1000万条数据执行时间: {estimated_time:.2f} 秒")
    
    if estimated_time < 60:
        print("✅ 1000万条数据可以在合理时间内处理完成")
    else:
        print("⚠️  1000万条数据可能需要较长时间处理")


def explain_optimization():
    """解释优化原理"""
    print(f"\n{'='*80}")
    print("优化原理解释")
    print(f"{'='*80}")
    
    print("""
原代码的问题：
1. 时间复杂度为 O(n²)（双重循环）加上 O(n)（检查重复）
   - 实际复杂度接近 O(n³)
   - 对于10,000,000条数据，需要约10^21次操作
   - 这在现代计算机上是不可行的

优化策略：

1. 集合（Set）方法：
   - 利用哈希集合的 O(1) 查找特性
   - 总体时间复杂度降至 O(n)
   - 空间复杂度 O(n)

2. 计数器（Counter）方法：
   - 一次性统计所有元素的出现次数
   - 然后筛选出现次数 > 1 的元素
   - 时间复杂度 O(n)，空间复杂度 O(n)

3. 字典（Dictionary）方法：
   - 使用字典记录每个元素的出现次数
   - 原理与Counter类似，但实现更底层
   - 时间复杂度 O(n)，空间复杂度 O(n)

性能对比估算：
- 原始方法：10,000条数据 ≈ 1秒
            100,000条数据 ≈ 100秒
            1,000,000条数据 ≈ 10,000秒（约2.8小时）
            10,000,000条数据 ≈ 1,000,000秒（约11.6天）

- 优化方法：10,000条数据 ≈ 0.001秒
            100,000条数据 ≈ 0.01秒
            1,000,000条数据 ≈ 0.1秒
            10,000,000条数据 ≈ 1秒

总结：优化后的算法将时间复杂度从O(n³)降低到O(n)，
在1000万条数据上可以从几天降低到几秒钟！
    """)


if __name__ == "__main__":
    # 设置随机种子以确保结果可重现
    random.seed(42)
    
    # 测试性能
    test_performance()
    
    # 测试大数据集
    test_large_dataset()
    
    # 解释优化原理
    explain_optimization()
    
    print("\n推荐使用优化版本2（Counter方法），因为它最简洁、最Pythonic，且性能优秀。")