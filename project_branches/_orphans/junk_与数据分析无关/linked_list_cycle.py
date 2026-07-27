class ListNode:
    """单链表节点定义"""
    def __init__(self, x):
        self.val = x
        self.next = None


def detect_cycle(head):
    """
    判断单链表是否有环，并返回环的入口节点
    
    参数:
    head: 链表头节点
    
    返回:
    如果有环，返回环的入口节点；如果没有环，返回None
    
    时间复杂度: O(n)
    空间复杂度: O(1)
    """
    if not head or not head.next:
        return None
    
    # 使用快慢指针判断是否有环
    slow = head
    fast = head
    
    has_cycle = False
    while fast and fast.next:
        slow = slow.next          # 慢指针每次走一步
        fast = fast.next.next    # 快指针每次走两步
        
        if slow == fast:
            has_cycle = True
            break
    
    # 如果没有环，返回None
    if not has_cycle:
        return None
    
    # 找到环的入口节点
    # 将其中一个指针重新指向链表头，然后以相同速度前进
    fast = head
    while fast != slow:
        fast = fast.next
        slow = slow.next
    
    return slow


def create_linked_list_with_cycle(values, cycle_pos):
    """
    创建一个带环的链表用于测试
    
    参数:
    values: 链表节点的值列表
    cycle_pos: 环的入口节点位置（从0开始），设置为-1表示无环
    
    返回:
    链表头节点
    """
    if not values:
        return None
    
    # 创建链表节点
    nodes = [ListNode(val) for val in values]
    
    # 连接节点
    for i in range(len(nodes) - 1):
        nodes[i].next = nodes[i + 1]
    
    # 如果有环，尾节点指向环的入口
    if cycle_pos >= 0 and cycle_pos < len(nodes):
        nodes[-1].next = nodes[cycle_pos]
    
    return nodes[0]


def print_list(head, max_nodes=20):
    """
    打印链表（为避免死循环，最多打印max_nodes个节点）
    """
    nodes = []
    current = head
    count = 0
    
    while current and count < max_nodes:
        nodes.append(str(current.val))
        current = current.next
        count += 1
        
        # 如果节点数达到上限且链表还未结束，说明可能有环
        if count == max_nodes and current:
            nodes.append("...")
            break
    
    print(" -> ".join(nodes))


def test_detect_cycle():
    """测试函数"""
    print("===== 测试检测链表环 =====")
    
    # 测试用例1: 无环链表
    print("\n测试用例1: 无环链表 [1 -> 2 -> 3 -> 4 -> 5]")
    head1 = create_linked_list_with_cycle([1, 2, 3, 4, 5], -1)
    result1 = detect_cycle(head1)
    print(f"结果: {result1.val if result1 else 'None'}")
    
    # 测试用例2: 有环链表，环的入口是第1个节点（位置0）
    print("\n测试用例2: 有环链表 [1 -> 2 -> 3 -> 4 -> 5 -> 回到1]")
    head2 = create_linked_list_with_cycle([1, 2, 3, 4, 5], 0)
    result2 = detect_cycle(head2)
    print(f"结果: {result2.val if result2 else 'None'}")
    
    # 测试用例3: 有环链表，环的入口是第3个节点（位置2）
    print("\n测试用例3: 有环链表 [1 -> 2 -> 3 -> 4 -> 5 -> 回到3]")
    head3 = create_linked_list_with_cycle([1, 2, 3, 4, 5], 2)
    result3 = detect_cycle(head3)
    print(f"结果: {result3.val if result3 else 'None'}")
    
    # 测试用例4: 有环链表，环的入口是最后一个节点（位置4）
    print("\n测试用例4: 有环链表 [1 -> 2 -> 3 -> 4 -> 5 -> 回到5]")
    head4 = create_linked_list_with_cycle([1, 2, 3, 4, 5], 4)
    result4 = detect_cycle(head4)
    print(f"结果: {result4.val if result4 else 'None'}")
    
    # 测试用例5: 单节点无环
    print("\n测试用例5: 单节点无环链表 [1]")
    head5 = create_linked_list_with_cycle([1], -1)
    result5 = detect_cycle(head5)
    print(f"结果: {result5.val if result5 else 'None'}")
    
    # 测试用例6: 单节点自环
    print("\n测试用例6: 单节点自环链表 [1 -> 回到1]")
    head6 = create_linked_list_with_cycle([1], 0)
    result6 = detect_cycle(head6)
    print(f"结果: {result6.val if result6 else 'None'}")
    
    # 测试用例7: 空链表
    print("\n测试用例7: 空链表")
    head7 = create_linked_list_with_cycle([], -1)
    result7 = detect_cycle(head7)
    print(f"结果: {result7.val if result7 else 'None'}")


if __name__ == "__main__":
    test_detect_cycle()