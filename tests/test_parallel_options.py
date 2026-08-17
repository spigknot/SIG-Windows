"""Opções de Conversões paralelas: n/2, n, 2n e 4n núcleos."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sig_app import cpu_parallel_options  # noqa: E402


class CpuParallelOptionsTest(unittest.TestCase):
    def test_six_cores(self):
        self.assertEqual(cpu_parallel_options(6), [3, 6, 12, 24])

    def test_xeon_eighteen_cores(self):
        self.assertEqual(cpu_parallel_options(18), [9, 18, 36, 72])

    def test_single_core_collapses(self):
        options = cpu_parallel_options(1)
        self.assertEqual(options, sorted(set(options)))
        self.assertTrue(all(value >= 1 for value in options))

    def test_odd_cores(self):
        options = cpu_parallel_options(3)
        self.assertIn(1, options)
        self.assertIn(3, options)
        self.assertIn(6, options)
        self.assertIn(12, options)


if __name__ == "__main__":
    unittest.main()
