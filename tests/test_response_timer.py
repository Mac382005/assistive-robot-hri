import time
import unittest

from experiment.response_timer import ResponseTimer


class ResponseTimerTests(unittest.TestCase):
    def test_timer_records_positive_elapsed_time(self):
        timer = ResponseTimer()
        timer.start()
        time.sleep(0.01)
        result = timer.stop()
        self.assertGreaterEqual(result["response_time_ms"], 1)
        self.assertIn("started_at", result)
        self.assertIn("acknowledged_at", result)

    def test_stop_before_start_raises(self):
        timer = ResponseTimer()
        with self.assertRaises(RuntimeError):
            timer.stop()


if __name__ == "__main__":
    unittest.main()
