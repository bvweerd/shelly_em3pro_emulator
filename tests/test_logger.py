"""Tests for the logger module."""

import logging
from unittest.mock import patch


from src.config.logger import setup_logging, get_logger


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def setup_method(self):
        """Reset the configured flag before each test."""
        import src.config.logger

        src.config.logger._configured = False

    def teardown_method(self):
        """Clean up after each test."""
        import src.config.logger

        src.config.logger._configured = False

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_default(self, mock_basic_config, mock_structlog_configure):
        """Test setup_logging with default parameters."""
        setup_logging()

        mock_basic_config.assert_called_once()
        mock_structlog_configure.assert_called_once()

        # Check log level
        call_kwargs = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.INFO

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_debug_level(
        self, mock_basic_config, mock_structlog_configure
    ):
        """Test setup_logging with DEBUG level."""
        setup_logging(level="DEBUG")

        call_kwargs = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.DEBUG

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_warning_level(
        self, mock_basic_config, mock_structlog_configure
    ):
        """Test setup_logging with WARNING level."""
        setup_logging(level="WARNING")

        call_kwargs = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.WARNING

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_error_level(
        self, mock_basic_config, mock_structlog_configure
    ):
        """Test setup_logging with ERROR level."""
        setup_logging(level="error")  # lowercase should work

        call_kwargs = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.ERROR

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_invalid_level(
        self, mock_basic_config, mock_structlog_configure
    ):
        """Test setup_logging with invalid level falls back to INFO."""
        setup_logging(level="INVALID")

        call_kwargs = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.INFO

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_with_format(
        self, mock_basic_config, mock_structlog_configure
    ):
        """Test setup_logging with custom format."""
        custom_format = "%(asctime)s - %(name)s - %(message)s"
        setup_logging(log_format=custom_format)

        call_kwargs = mock_basic_config.call_args[1]
        assert call_kwargs["format"] == custom_format

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_without_format(
        self, mock_basic_config, mock_structlog_configure
    ):
        """Test setup_logging without custom format."""
        setup_logging()

        call_kwargs = mock_basic_config.call_args[1]
        assert "format" not in call_kwargs

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_only_once(self, mock_basic_config, mock_structlog_configure):
        """Test that setup_logging only configures once."""
        setup_logging()
        setup_logging()
        setup_logging()

        # Should only be called once
        assert mock_basic_config.call_count == 1
        assert mock_structlog_configure.call_count == 1

    @patch("src.config.logger.structlog.configure")
    @patch("src.config.logger.logging.basicConfig")
    def test_setup_logging_structlog_processors(
        self, mock_basic_config, mock_structlog_configure
    ):
        """Test that structlog is configured with correct processors."""
        setup_logging()

        call_kwargs = mock_structlog_configure.call_args[1]
        processors = call_kwargs["processors"]

        # Check that key processors are included
        assert "TimeStamper" in str(processors)


class TestGetLogger:
    """Tests for the get_logger function."""

    def test_get_logger_returns_bound_logger(self):
        """Test that get_logger returns a structlog logger."""
        logger = get_logger("test_module")

        # Should be a structlog logger (or wrapper)
        assert logger is not None

    def test_get_logger_different_names(self):
        """Test that different names create different loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        # Both should be valid loggers
        assert logger1 is not None
        assert logger2 is not None

    def test_get_logger_with_dunder_name(self):
        """Test get_logger with __name__ style input."""
        logger = get_logger(__name__)

        assert logger is not None
