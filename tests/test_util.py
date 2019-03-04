"""Test various api functions."""

import unittest
from unittest import mock
import time
from blinkpy.helpers.util import Throttle


class TestUtil(unittest.TestCase):
    """Test the helpers/util module."""

    def setUp(self):
        """Initialize the blink module."""

    def tearDown(self):
        """Tear down blink module."""

    def test_throttle(self):
        """Test the throttle decorator."""
        calls = []

        @Throttle(seconds=5)
        def test_throttle():
            calls.append(1)

        now = int(time.time())
        now_plus_four = now + 4
        now_plus_six = now + 6

        test_throttle()
        self.assertEqual(1, len(calls))

        # Call again, still shouldn't fire
        test_throttle()
        self.assertEqual(1, len(calls))

        # Call with force
        test_throttle(force=True)
        self.assertEqual(2, len(calls))

        # Call without throttle, shouldn't fire
        test_throttle()
        self.assertEqual(2, len(calls))

        # Fake time as 4 seconds from now
        with mock.patch('time.time', return_value=now_plus_four):
            test_throttle()
        self.assertEqual(2, len(calls))

        # Fake time as 6 seconds from now
        with mock.patch('time.time', return_value=now_plus_six):
            test_throttle()
        self.assertEqual(3, len(calls))

    def test_throttle_per_instance(self):
        """Test that throttle is done once per instance of class."""
        class Tester:
            """A tester class for throttling."""

            def test(self):
                """Test the throttle."""
                return True

        tester = Tester()
        throttled = Throttle(seconds=1)(tester.test)
        self.assertEqual(throttled(), True)
        self.assertEqual(throttled(), None)

    def test_throttle_on_two_methods(self):
        """Test that throttle works for multiple methods."""
        class Tester:
            """A tester class for throttling."""

            @Throttle(seconds=3)
            def test1(self):
                """Test function for throttle."""
                return True

            @Throttle(seconds=5)
            def test2(self):
                """Test function for throttle."""
                return True

        tester = Tester()
        now = time.time()
        now_plus_4 = now + 4
        now_plus_6 = now + 6

        self.assertEqual(tester.test1(), True)
        self.assertEqual(tester.test2(), True)
        self.assertEqual(tester.test1(), None)
        self.assertEqual(tester.test2(), None)

        with mock.patch('time.time', return_value=now_plus_4):
            self.assertEqual(tester.test1(), True)
            self.assertEqual(tester.test2(), None)

        with mock.patch('time.time', return_value=now_plus_6):
            self.assertEqual(tester.test1(), None)
            self.assertEqual(tester.test2(), True)
