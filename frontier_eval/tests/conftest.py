"""Shared pytest configuration for the frontier_eval test suite."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: end-to-end evaluator runs that drive a real simulator (tens of seconds)",
    )
