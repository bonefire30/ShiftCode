from __future__ import annotations

import importlib
import logging
import uuid
import unittest

import logging_config


class TestLoggingConfig(unittest.TestCase):
    def test_third_party_http_debug_loggers_are_suppressed(self) -> None:
        module = importlib.reload(logging_config)
        module.setup_logging(level="DEBUG")

        for name in ("openai", "openai._base_client", "httpcore", "httpx"):
            logger = logging.getLogger(name)
            self.assertGreaterEqual(logger.level, logging.WARNING)
            self.assertFalse(logger.propagate)

    def test_json_formatter_redacts_secrets(self) -> None:
        formatter = logging_config._JsonFormatter()  # noqa: SLF001
        record = logging.LogRecord(
            name="shiftcode.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="MINIMAX_API_KEY=TEST_REDACT_ME",
            args=(),
            exc_info=None,
        )
        rendered = formatter.format(record)
        self.assertNotIn("TEST_REDACT_ME", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_third_party_debug_does_not_enter_run_log(self) -> None:
        module = importlib.reload(logging_config)
        module.setup_logging(level="DEBUG")
        handler = module.attach_per_run_file_handler(
            thread_id=f"unit-{uuid.uuid4().hex[:8]}",
            prefix="unit_logging",
            level="DEBUG",
        )
        path = handler.baseFilename
        try:
            logging.getLogger("httpcore").debug("HTTP request MINIMAX_API_KEY=TEST_REDACT_ME")
            logging.getLogger("shiftcode.test").info("safe app log")
        finally:
            module.detach_per_run_file_handler(handler)

        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("safe app log", text)
        self.assertNotIn("HTTP request", text)
        self.assertNotIn("TEST_REDACT_ME", text)


if __name__ == "__main__":
    unittest.main()
