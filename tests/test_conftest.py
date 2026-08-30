"""验证 conftest 的 sleep 截断 fixture 生效。"""

import time


def test_sleep_is_capped_by_conftest():
    import tests.conftest as conftest

    start = time.perf_counter()
    time.sleep(conftest._MAX_TEST_SLEEP_SECONDS * 1000)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"sleep 未被截断,实际耗时 {elapsed:.2f}s"
