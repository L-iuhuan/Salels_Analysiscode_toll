def find_majority_element(nums):
    """
    找出数组中出现次数超过数组长度一半的元素
    
    参数:
    nums: 整数数组
    
    返回:
    出现次数超过数组长度一半的元素，如果没有则返回None
    
    时间复杂度: O(n)
    空间复杂度: O(1)
    """
    if not nums:
        return None
    
    # 第一轮：使用摩尔投票法找到候选元素
    candidate = None
    count = 0
    
    for num in nums:
        if count == 0:
            candidate = num
            count = 1
        elif num == candidate:
            count += 1
        else:
            count -= 1
    
    # 第二轮：验证候选元素是否真的出现次数超过一半
    if count == 0:
        return None
    
    # 统计候选元素的实际出现次数
    actual_count = 0
    for num in nums:
        if num == candidate:
            actual_count += 1
    
    # 检查是否超过数组长度的一半
    if actual_count > len(nums) // 2:
        return candidate
    else:
        return None


# 测试用例
def test_find_majority_element():
    # 测试用例1：存在多数元素
    test1 = [2, 2, 1, 1, 1, 2, 2]
    result1 = find_majority_element(test1)
    print(f"测试用例1: {test1} -> 结果: {result1}")  # 应该返回 2
    
    # 测试用例2：存在多数元素
    test2 = [3, 3, 4, 2, 4, 4, 2, 4, 4]
    result2 = find_majority_element(test2)
    print(f"测试用例2: {test2} -> 结果: {result2}")  # 应该返回 4
    
    # 测试用例3：不存在多数元素
    test3 = [1, 2, 3, 4, 5]
    result3 = find_majority_element(test3)
    print(f"测试用例3: {test3} -> 结果: {result3}")  # 应该返回 None
    
    # 测试用例4：空数组
    test4 = []
    result4 = find_majority_element(test4)
    print(f"测试用例4: {test4} -> 结果: {result4}")  # 应该返回 None
    
    # 测试用例5：所有元素相同
    test5 = [1, 1, 1, 1]
    result5 = find_majority_element(test5)
    print(f"测试用例5: {test5} -> 结果: {result5}")  # 应该返回 1
    
    # 测试用例6：刚好一半的情况（不应该返回）
    test6 = [1, 1, 2, 2]
    result6 = find_majority_element(test6)
    print(f"测试用例6: {test6} -> 结果: {result6}")  # 应该返回 None


if __name__ == "__main__":
    test_find_majority_element()