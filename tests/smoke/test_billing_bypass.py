
import os
import unittest
from quentin.infra.billing.balance_manager import balance_manager

class TestBillingBypass(unittest.TestCase):
    def test_infinite_balance_init(self):
        """
        验证 BalanceManager 能够被初始化并允许扣费。
        """
        user_id = "smoke_test_user"
        # 1. 初始状态应该是 0 或无法扣费
        balance_manager.set_balance(user_id, 0.0)
        can_deduct = balance_manager.deduct_realtime(user_id, tokens=100)
        self.assertFalse(can_deduct, "余额为 0 时不应允许扣费")

        # 2. 设置“无限”余额
        balance_manager.set_balance(user_id, 999999.0)
        can_deduct = balance_manager.deduct_realtime(user_id, tokens=100)
        self.assertTrue(can_deduct, "设置余额后应允许扣费")
        
        current_balance = balance_manager.get_balance(user_id)
        self.assertLess(current_balance, 999999.0, "余额应该有所减少")
        print(f"✅ Smoke Test Passed: Balance after deduction is {current_balance}")

if __name__ == "__main__":
    unittest.main()
