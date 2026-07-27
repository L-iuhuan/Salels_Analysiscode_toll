import threading
import time


def demonstrate_race_condition():
    """演示竞态条件问题"""
    print("===== 演示竞态条件问题 =====")
    
    counter = 0

    def increment():
        nonlocal counter
        for _ in range(100000):
            counter += 1

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


def solve_with_lock():
    """使用锁解决竞态条件"""
    print("\n===== 使用锁解决竞态条件 =====")
    
    counter = 0
    lock = threading.Lock()

    def increment():
        nonlocal counter
        for _ in range(100000):
            with lock:  # 使用锁保护临界区
                counter += 1

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


def solve_with_thread_safe_counter():
    """使用线程安全的数据结构"""
    def solve_with_thread_safe_counter():
        """使用线程安全的数据结构"""
        print("\n===== 使用线程安全数据结构 =====")
        
        from threading import Thread
        from queue import Queue
        
        # 使用队列实现线程安全的计数
        q = Queue()
        counter = 0
    
        def increment():
            for _ in range(100000):
                q.put(1)
    
        def process_queue():
            nonlocal counter
            while True:
                try:
                    item = q.get_nowait()
                    counter += item
                    q.task_done()
                except:
                    break
    
        threads = [Thread(target=increment) for _ in range(10)]
        process_thread = Thread(target=process_queue)
        
        start_time = time.time()
        for t in threads:
            t.start()
        
        process_thread.start()
        
        for t in threads:
            t.join()
        
        # 等待队列中的所有项目被处理
        q.join()
        process_thread.join()
        
        end_time = time.time()
        
        print(f"预期结果: 1000000")
        print(f"实际结果: {counter}")
        print(f"时间消耗: {end_time - start_time:.4f}秒")
        print(f"差值: {1000000 - counter}")
def solve_with_atomic_operations():
    def solve_with_atomic_operations():
        """使用原子操作"""
        print("\n===== 使用原子操作 =====")
        
        import threading
        
        # 使用 threading.Lock 实现原子操作
        counter = 0
        lock = threading.Lock()
        
        def increment():
            nonlocal counter
            for _ in range(100000):
                # 使用锁实现原子操作
                lock.acquire()
                counter += 1
                lock.release()
    
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

def solve_with_queue():
    """使用队列（Queue）解决竞态条件"""
    print("\n===== 使用队列（Queue）解决竞态条件 =====")
    
    import queue
    
    q = queue.Queue()
    counter = 0

    def increment():
        for _ in range(100000):
            q.put(1)

    def process_queue():
        nonlocal counter
        while True:
            try:
                # 设置超时，避免无限等待
                item = q.get(timeout=1)
                counter += item
                q.task_done()
            except queue.Empty:
                break

    # 创建10个增量线程
    threads = [threading.Thread(target=increment) for _ in range(10)]
    
    # 创建1个处理队列的线程
    process_thread = threading.Thread(target=process_queue)
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    process_thread.start()
    
    for t in threads:
        t.join()
    
    process_thread.join()
    end_time = time.time()
    
    print(f"预期结果: 1000000")
    print(f"实际结果: {counter}")
    print(f"时间消耗: {end_time - start_time:.4f}秒")
    print(f"差值: {1000000 - counter}")


def explain_race_condition():
    """解释竞态条件的原理"""
    print("\n===== 竞态条件原理解释 =====")
    print("""
竞态条件（Race Condition）是指：

当多个线程同时访问和修改共享资源时，由于执行时序的不确定性，
导致程序执行结果与预期不符的情况。

在Python中的这个例子中：

counter += 1 不是一个原子操作！它包含三个步骤：
1. 读取counter的当前值（例如：100）
2. 将值加1（例如：101）
3. 将新值写回counter（例如：101）

竞态场景示例：
- 线程A读取了counter的值（100）
- 在线程A将值加1并写回之前，线程B也读取了counter的值（仍然是100）
- 线程A将101写回counter
- 线程B也将101写回counter
- 结果：两个线程执行了两次increment操作，但counter只增加了1

解决方案：
1. 使用锁（Lock）：保护临界区，确保同一时间只有一个线程可以访问
2. 使用线程安全的数据结构：如Queue、Counter等
3. 使用原子操作：确保操作是不可分割的
4. 使用队列：通过消息传递避免直接共享状态

每种方案都有其适用场景和性能特点：
- 锁最简单但可能影响性能
- 队列适合生产者-消费者模式
- 原子操作性能最好但适用范围有限
    """)


if __name__ == "__main__":
    # 演示竞态条件问题
    demonstrate_race_condition()
    
    # 演示解决方案
    solve_with_lock()
    solve_with_thread_safe_counter()
    solve_with_atomic_operations()
    solve_with_queue()
    
    # 解释原理
    explain_race_condition()