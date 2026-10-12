import unittest
from classifier import TrafficClassifier
from config import WARMUP_WINDOWS, CONSECUTIVE

class TestTrafficClassifier(unittest.TestCase):
    def test_warmup(self):
        classifier = TrafficClassifier()
        # Even with extremely high metrics, the initial windows should be WARMUP
        high_metrics = {'packet_rate': 10000, 'throughput_kbps': 10000, 'retx_ratio': 1.0}
        
        for _ in range(WARMUP_WINDOWS):
            level, _, _ = classifier.classify(high_metrics)
            self.assertEqual(level, 'WARMUP')
            
        # The very next window should not be warmup
        level, _, _ = classifier.classify(high_metrics)
        self.assertNotEqual(level, 'WARMUP')

    def test_progression_normal_warning_congested(self):
        classifier = TrafficClassifier()
        
        # 1. Complete warmup with normal traffic
        normal = {'packet_rate': 50, 'throughput_kbps': 200, 'retx_ratio': 0.01}
        for _ in range(WARMUP_WINDOWS):
            classifier.classify(normal)
            
        # 2. Test NORMAL state
        level, over, _ = classifier.classify(normal)
        self.assertEqual(level, 'NORMAL')
        self.assertEqual(len(over), 0)
        
        # 3. Test WARNING state (Only 1 parameter over threshold)
        warning_metrics = {'packet_rate': 10000, 'throughput_kbps': 200, 'retx_ratio': 0.01}
        level, over, _ = classifier.classify(warning_metrics)
        self.assertEqual(level, 'WARNING')
        self.assertEqual(len(over), 1)
        
        # 4. Test WARNING state (2 parameters over, but short burst = not enough consecutive windows)
        burst = {'packet_rate': 10000, 'throughput_kbps': 5000, 'retx_ratio': 0.01}
        level, over, _ = classifier.classify(burst)
        self.assertEqual(level, 'WARNING')
        
        # 5. Test CONGESTED state (2+ parameters over threshold for CONSECUTIVE windows)
        # We already had 1 window of 'burst'. We need (CONSECUTIVE - 1) more to trigger congested.
        for _ in range(CONSECUTIVE - 2): 
            level, over, _ = classifier.classify(burst)
            self.assertEqual(level, 'WARNING')
            
        # The final one in the streak should trigger CONGESTED
        level, over, _ = classifier.classify(burst)
        self.assertEqual(level, 'CONGESTED')
        
        # 6. Fall back to NORMAL immediately when traffic drops
        level, over, _ = classifier.classify(normal)
        self.assertEqual(level, 'NORMAL')

if __name__ == '__main__':
    unittest.main()
