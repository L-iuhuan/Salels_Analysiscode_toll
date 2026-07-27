def safe_divide(a, b, default=0):
    """
    安全除法函数
    
    参数:
    a: 被除数
    b: 除数
    default: 默认值，当除数是0或操作数不是数字时返回
    
    返回:
    正常情况下返回 a/b
    当 b=0 或 a,b 不是数字时返回 default
    当结果溢出时返回 float('inf') 或 float('-inf')
    """
    try:
        # 检查a和b是否是数字
        if not (isinstance(a, (int, float, complex)) and isinstance(b, (int, float, complex))):
            return default
        
        # 执行除法
        result = a / b
        
        # 检查溢出 (Python会自动处理，返回inf或-inf)
        return result
    except:
        return default


# 一行代码实现
safe_divide_one_line = lambda a, b, default=0: a / b if isinstance(a, (int, float, complex)) and isinstance(b, (int, float, complex)) and b != 0 else default


def test_safe_divide():
    """测试safe_divide函数的各种情况"""
    
    test_cases = [
        # (a, b, expected_result, description)
        (10, 2, 5.0, "正常除法"),
        (10, 0, 0, "除数为0"),
        (0, 5, 0.0, "被除数为0"),
        (-10, 2, -5.0, "负数除法"),
        (10, -2, -5.0, "负除数"),
        (-10, -2, 5.0, "两个负数"),
        (10.5, 2, 5.25, "浮点数除法"),
        (10, 3, 10 / 3, "不整除"),
        ("10", 2, 0, "a不是数字"),
        (10, "2", 0, "b不是数字"),
        ("abc", "def", 0, "两个都不是数字"),
        (None, 2, 0, "a是None"),
        (10, None, 0, "b是None"),
        (1e308, 1e-308, float('inf'), "上溢出"),
        (-1e308, 1e-308, float('-inf'), "下溢出"),
        (0, 0, 0, "0除以0"),
        (float('inf'), 1, float('inf'), "无穷大除法"),
        (1, float('inf'), 0.0, "除以无穷大"),
    ]
    
    print("测试标准实现:")
    print("=" * 80)
    for i, (a, b, expected, description) in enumerate(test_cases, 1):
        result = safe_divide(a, b)
        # 使用float类型进行比较，忽略int和float的类型差异
        status = "✅" if float(result) == float(expected) else "❌"
        print(f"测试 {i:2d}: {status} {description}")
        print(f"        输入: a={a}, b={b}")
        print(f"        预期: {expected}")
        print(f"        实际: {result}")
        if status == "❌":
            print(f"        差异: 预期 {expected} != 实际 {result}")
        print()
    
    print("\n测试一行代码实现:")
    print("=" * 80)
    for i, (a, b, expected, description) in enumerate(test_cases, 1):
        result = safe_divide_one_line(a, b)
        # 使用float类型进行比较，忽略int和float的类型差异
        status = "✅" if float(result) == float(expected) else "❌"
        print(f"测试 {i:2d}: {status} {description}")
        print(f"        输入: a={a}, b={b}")
        print(f"        预期: {expected}")
        print(f"        实际: {result}")
        if status == "❌":
            print(f"        差异: 预期 {expected} != 实际 {result}")
        print()


def custom_default_test():
    """测试自定义默认值"""
    print("测试自定义默认值:")
    print("=" * 80)
    
    test_cases = [
        (10, 0, -1),
        ("10", 2, "error"),
        (None, 5, None),
    ]
    
    for a, b, custom_default in test_cases:
        result = safe_divide(a, b, custom_default)
        print(f"safe_divide({a}, {b}, {custom_default}) = {result}")
        
        # 一行代码版本
        result_one_line = safe_divide_one_line(a, b, custom_default)
        print(f"一行代码版本: safe_divide_one_line({a}, {b}, {custom_default}) = {result_one_line}")
        print()


if __name__ == "__main__":
    # 运行测试
    test_safe_divide()
    custom_default_test()
    
    print("注意：Python中浮点数溢出会自动转换为inf或-inf，所以不需要特别处理。")
    print("一行代码实现通过条件表达式完成了所有检查，更加简洁。")