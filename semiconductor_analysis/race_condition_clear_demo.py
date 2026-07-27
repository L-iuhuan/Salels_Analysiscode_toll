import threading
import time


def race_condition_demo():
    """演示竞态条件问题"""
    print("===== 演示竞态条件问题 =====")
    
    # 使用全局变量，更容易触发竞态条件
    global counter
    counter = 0

    def increment():
        global counter
        for _ in range(100000):
            # 这个操作不是原子的，会触发竞态条件
            counter += 1

    # 创建多个线程
    threads = [threading.Thread(target=increment) for _ in range(10)]
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    end_time = time.time()
    
    print(f"预期结果: 1000000")
    print(f"实际结果: {counter}")
    print(f"时间消耗: {end_time - start_time:.4f}秒")
    print(f"差值: {1000000 - counter}")
    
    if counter != 1000000:
        print("⚠️  竞态条件导致结果不正确！")
    else:
        print("✅ 结果正确（这次运气好，没有触发竞态条件）")


def race_condition_with_shared_list():
    """使用共享列表更明显地演示竞态条件"""
    print("\n===== 使用共享列表演示竞态条件 =====")
    
    # 共享列表
    shared_list = []
    list_len = 0

    def append_to_list():
        nonlocal list_len
        for i in range(1000):
            shared_list.append(i)
            # 模拟计算并更新长度
            list_len = len(shared_list)
            time.sleep(0.0001)  # 增加竞态条件的概率

    threads = [threading.Thread(target=append_to_list) for _ in range(5)]
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    end_time = time.time()
    
    expected_length = 5 * 1000
    actual_length = len(shared_list)
    
    print(f"预期列表长度: {expected_length}")
    print(f"实际列表长度: {actual_length}")
    print(f"时间消耗: {end_time - start_time:.4f}秒")
    
    if actual_length != expected_length:
        print("⚠️  竞态条件导致结果不正确！")
    else:
        print("✅ 结果正确（这次运气好，没有触发竞态条件）")


def solve_with_lock():
    """使用锁解决竞态条件"""
    print("\n===== 使用锁解决竞态条件 =====")
    
    global counter_safe
    counter_safe = 0
    lock = threading.Lock()

    def increment():
        global counter_safe
        for _ in range(100000):
            # 使用锁保护临界区
            with lock:
                counter_safe += 1

    threads = [threading.Thread(target=increment) for _ in range(10)]
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    end_time = time.time()
    
    print(f"预期结果: 1000000")
    print(f"实际结果: {counter_safe}")
    print(f"时间消耗: {end_time - start_time:.4f}秒")
    print(f"差值: {1000000 - counter_safe}")
    
    if counter_safe == 1000000:
        print("✅ 使用锁成功解决了竞态条件！")
    else:
        print("❌ 仍然有问题")


def solve_with_atomic():
    """使用原子操作（Python中的atomic操作）"""
    print("\n===== 使用原子操作 =====")
    
    # 使用threading.local创建线程局部变量，避免共享状态
    thread_local = threading.local()
    results = []
    results_lock = threading.Lock()

    def increment():
        # 每个线程有自己的计数器
        thread_local.counter = 0
        for _ in range(100000):
            thread_local.counter += 1
        
        # 最后将结果汇总到共享列表
        with results_lock:
            results.append(thread_local.counter)

    threads = [threading.Thread(target=increment) for _ in range(10)]
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    # 计算总和
    total = sum(results)
    end_time = time.time()
    
    print(f"预期结果: 1000000")
    print(f"实际结果: {total}")
    print(f"时间消耗: {end_time - start_time:.4f}秒")
    print(f"差值: {1000000 - total}")
    
    if total == 1000000:
        print("✅ 通过线程局部变量避免了竞态条件！")
    else:
        print("❌ 仍然有问题")


def explain_race_condition():
    """解释竞态条件的原理"""
    print("\n===== 竞态条件原理解释 =====")
    print("""
竞态条件（Race Condition）的本质问题：

1. 为什么会出现竞态条件？
   - 多个线程同时访问共享资源
   - 操作不是原子的（可以分解为多个步骤）
   - 操作的执行顺序不确定

2. 在Python中的具体表现：
   counter += 1 这个看似简单的操作，实际上是三个步骤：
   
   步骤1：读取counter的当前值
      temp = counter
   
   步骤2：对值进行加1操作
      temp = temp + 1
   
   步骤3：将新值写回counter
      counter = temp

3. 竞态场景示例：
   - 线程A执行步骤1，读取counter=100
   - 线程B执行步骤1，读取counter=100（因为A还没更新）
   - 线程A执行步骤2和3，counter变为101
   - 线程B执行步骤2和3，counter变为101（覆盖了A的结果）
   - 结果：两个线程执行了两次increment，counter只增加了1

4. 为什么有时能正确运行？
   - 竞态条件是概率性的，不是必然发生的
   - 线程调度、CPU时间片分配等因素影响是否发生
   - 单次测试不能证明没有竞态条件

5. 解决方案的核心思想：
   - 锁（Lock）：强制串行化访问共享资源
   - 线程局部变量：避免共享状态
   - 原子操作：确保操作不可分割
   - 消息传递：通过队列等机制避免直接共享

记住：没有万能的解决方案，需要根据具体场景选择合适的方法！
    """)


if __name__ == "__main__":
    # 演示竞态条件问题
    race_condition_demo()
    
    # 使用共享列表演示
    race_condition_with_shared_list()
    
    # 演示解决方案
    solve_with_lock()
    solve_with_atomic()
    
    # 解释原理
    explain_race_condition()