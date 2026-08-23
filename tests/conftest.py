from __future__ import annotations

import os


def pytest_addoption(parser):
    parser.addoption(
        "--native-mode",
        action="store",
        default=None,
        choices=["python", "native", "compare", "auto"],
        help="Force MASKIT_NATIVE for this pytest run.",
    )


def pytest_configure(config):
    mode = config.getoption("--native-mode")
    if mode:
        os.environ["MASKIT_NATIVE"] = mode
