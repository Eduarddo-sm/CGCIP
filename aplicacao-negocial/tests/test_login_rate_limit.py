import unittest

from backend.services.login_rate_limit import LoginRateLimiter


class LoginRateLimiterTest(unittest.TestCase):
    def test_blocks_after_configured_failures_and_success_clears_state(self):
        limiter = LoginRateLimiter(max_attempts=2, block_seconds=60)
        self.assertEqual(limiter.failure("ip:user"), 0)
        self.assertEqual(limiter.failure("ip:user"), 60)
        self.assertGreater(limiter.retry_after("ip:user"), 0)
        limiter.success("ip:user")
        self.assertEqual(limiter.retry_after("ip:user"), 0)


if __name__ == "__main__":
    unittest.main()
