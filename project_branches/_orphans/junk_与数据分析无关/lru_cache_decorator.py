import threading
import time
from collections import OrderedDict
from functools import wraps


def lru_cache(maxsize=128):
    """
    LRU缓存装饰器
    
    参数:
    maxsize: 最大缓存大小，默认为128
    
    特性:
    - 缓存最近使用的maxsize个结果
    - 支持任意可哈希参数
    - 线程安全
    - 提供缓存命中率统计
    """
    def decorator(func):
        cache = OrderedDict()  # 使用OrderedDict实现LRU
        # 锁用于线程安全
        lock = threading.RLock()
        # 缓存统计信息
        cache_stats = {
            'hits': 0,        # 缓存命中次数
            'misses': 0,      # 缓存未命中次数
            'maxsize': maxsize, # 最大缓存大小
            'currsize': 0,    # 当前缓存大小
        }

        @wraps(func)
        def wrapper(*args, **kwargs):
            # 创建缓存键
            key = (args, frozenset(kwargs.items()))
            
            with lock:
                # 尝试从缓存获取结果
                if key in cache:
                    # 命中缓存
                    cache_stats['hits'] += 1
                    # 将访问的项移动到末尾（表示最近使用）
                    cache.move_to_end(key)
                    return cache[key]
                
                # 未命中缓存
                cache_stats['misses'] += 1
                
                # 执行函数获取结果
                result = func(*args, **kwargs)
                
                # 将结果存入缓存
                cache[key] = result
                # 将新项移动到末尾（表示最近使用）
                cache.move_to_end(key)
                
                # 检查缓存大小，如果超过限制则删除最久未使用的项
                if len(cache) > maxsize:
                    cache.popitem(last=False)  # 删除最久未使用的项
                
                # 更新当前缓存大小
                cache_stats['currsize'] = len(cache)
                
                return result
        
        # 添加缓存信息获取方法
        def get_cache_info():
            with lock:
                total = cache_stats['hits'] + cache_stats['misses']
                hit_rate = cache_stats['hits'] / total if total > 0 else 0
                return {
                    'hits': cache_stats['hits'],
                    'misses': cache_stats['misses'],
                    'hit_rate': hit_rate,
                    'maxsize': cache_stats['maxsize'],
                    'currsize': cache_stats['currsize'],
                }
        
        # 添加缓存清空方法
        def clear_cache():
            with lock:
                cache.clear()
                cache_stats['hits'] = 0
                cache_stats['misses'] = 0
                cache_stats['currsize'] = 0
        
        # 为包装函数添加方法
        wrapper.cache_info = get_cache_info
        wrapper.cache_clear = clear_cache
        
        return wrapper
    
    return decorator


# 测试函数
@lru_cache(maxsize=3)
def fibonacci(n):
    """计算斐波那契数列（用于测试缓存）"""
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)


@lru_cache(maxsize=5)
def slow_function(x, y=10, z=None):
    """模拟一个耗时函数"""
    time.sleep(0.1)  # 模拟耗时操作
    return x * y + (z or 0)


def test_lru_cache():
    """测试LRU缓存装饰器"""
    print("===== 测试LRU缓存装饰器 =====")
    
    # 测试1：斐波那契数列（验证递归调用缓存）
    print("\n测试1：斐波那契数列")
    start_time = time.time()
    result = fibonacci(20)
    end_time = time.time()
    print(f"fibonacci(20) = {result}")
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print("缓存信息:", fibonacci.cache_info())
    
    # 重置缓存
    fibonacci.cache_clear()
    
    # 测试2：多参数函数
    print("\n测试2：多参数函数")
    
    # 第一次调用 - 缓存未命中
    start_time = time.time()
    result = slow_function(2, 3)
    end_time = time.time()
    print(f"第一次调用 slow_function(2, 3) = {result}")
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print("缓存信息:", slow_function.cache_info())
    
    # 第二次调用相同参数 - 缓存命中
    start_time = time.time()
    result = slow_function(2, 3)
    end_time = time.time()
    print(f"第二次调用 slow_function(2, 3) = {result}")
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print("缓存信息:", slow_function.cache_info())
    
    # 调用不同参数 - 缓存未命中
    start_time = time.time()
    result = slow_function(4, 5)
    end_time = time.time()
    print(f"调用 slow_function(4, 5) = {result}")
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print("缓存信息:", slow_function.cache_info())
    
    # 测试3：LRU淘汰机制
    print("\n测试3：LRU淘汰机制（maxsize=5）")
    
    # 清空缓存
    slow_function.cache_clear()
    print("缓存已清空")
    
    # 调用多个不同的函数，使缓存达到最大容量
    for i in range(6):
        result = slow_function(i, i+1, z=i*2)
        print(f"调用 slow_function({i}, {i+1}, z={i*2}) = {result}")
        print(f"缓存信息: {slow_function.cache_info()}")
    
    # 再次调用第一个参数，检查是否已经被淘汰
    start_time = time.time()
    result = slow_function(0, 1, z=0)
    end_time = time.time()
    print(f"\n再次调用 slow_function(0, 1, z=0) = {result}")
    print(f"执行时间: {end_time - start_time:.4f}秒")
    print("缓存信息:", slow_function.cache_info())
    
    if end_time - start_time > 0.05:  # 如果执行时间大于0.05秒，说明缓存未命中
        print("✅ LRU淘汰机制正常工作")
    else:
        print("❌ LRU淘汰机制可能有问题")


def test_thread_safety():
    """测试线程安全性"""
    print("\n===== 测试线程安全性 =====")
    
    @lru_cache(maxsize=10)
    def counter_func(x):
        time.sleep(0.01)  # 短暂延迟增加竞态条件概率
        return x * 2
    
    # 清空缓存
    counter_func.cache_clear()
    
    results = []
    errors = []
    
    def worker(x):
        try:
            for _ in range(50):
                result = counter_func(x)
                results.append((x, result))
        except Exception as e:
            errors.append(str(e))
    
    # 创建多个线程同时调用函数
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    print(f"总调用次数: {len(results)}")
    print(f"错误数量: {len(errors)}")
    print(f"缓存信息: {counter_func.cache_info()}")
    
    if not errors:
        print("✅ 线程安全性测试通过")
    else:
        print("❌ 线程安全性测试失败")
        print("错误:", errors)


def test_various_arguments():
    """测试各种类型的参数"""
    print("\n===== 测试各种类型的参数 =====")
    
    @lru_cache(maxsize=5)
    def test_func(a, b, c=None, **kwargs):
        return (a, b, c, kwargs)
    
    # 测试不同类型的参数
    test_cases = [
        (1, "hello"),                    # 整数和字符串
        (3.14, True, None),              # 浮点数、布尔值和None
        ([1, 2, 3], {"key": "value"}),   # 列表和字典（这会报错，因为不可哈希）
        (tuple([1, 2, 3]), frozenset({1, 2, 3})),  # 元组和冻结集合
    ]
    
    for i, args in enumerate(test_cases):
        try:
            if len(args) == 2:
                result = test_func(args[0], args[1])
            else:
                result = test_func(args[0], args[1], args[2])
            print(f"测试用例 {i+1}: 成功 - {result}")
        except TypeError as e:
            print(f"测试用例 {i+1}: 失败 - {e}")
    
    print(f"\n缓存信息: {test_func.cache_info()}")


if __name__ == "__main__":
    # 运行所有测试
    test_lru_cache()
    test_thread_safety()
    test_various_arguments()
    
    print("\n===== 总结 =====")
    print("✅ LRU缓存装饰器实现完成，支持：")
    print("   - 缓存最近使用的maxsize个结果")
    print("   - 支持任意可哈希参数")
    print("   - 线程安全")
    print("   - 提供缓存命中率统计")