"""Tests for the shelly_device module."""

import time

import pytest

from src.emulator.shelly_device import ShellyDevice


class TestShellyDevice:
    """Tests for the ShellyDevice class."""

    def test_init(self):
        """Test ShellyDevice initialization."""
        device = ShellyDevice(
            device_id="test-device",
            device_name="Test Device",
            mac_address="AA:BB:CC:DD:EE:FF",
        )

        assert device.device_id == "test-device"
        assert device.device_name == "Test Device"
        assert device.mac_address == "AABBCCDDEEFF"  # Normalized

    def test_init_defaults(self):
        """Test ShellyDevice default values."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="112233445566",
        )

        assert device.model == "SPEM-003CEBEU"
        assert device.firmware_version == "1.1.0"
        assert device.hardware_version == "1.0"

    def test_init_mac_normalization_colons(self):
        """Test MAC address normalization with colons."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="aa:bb:cc:dd:ee:ff",
        )

        assert device.mac_address == "AABBCCDDEEFF"

    def test_init_mac_normalization_dashes(self):
        """Test MAC address normalization with dashes."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="AA-BB-CC-DD-EE-FF",
        )

        assert device.mac_address == "AABBCCDDEEFF"

    def test_init_mac_normalization_lowercase(self):
        """Test MAC address normalization to uppercase."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="aabbccddeeff",
        )

        assert device.mac_address == "AABBCCDDEEFF"

    def test_init_invalid_mac_too_short(self):
        """Test ShellyDevice with invalid MAC (too short)."""
        with pytest.raises(ValueError, match="Invalid MAC address"):
            ShellyDevice(
                device_id="test",
                device_name="Test",
                mac_address="AABBCC",
            )

    def test_init_invalid_mac_too_long(self):
        """Test ShellyDevice with invalid MAC (too long)."""
        with pytest.raises(ValueError, match="Invalid MAC address"):
            ShellyDevice(
                device_id="test",
                device_name="Test",
                mac_address="AABBCCDDEEFF00",
            )

    def test_mac_bytes(self):
        """Test mac_bytes property."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="AABBCCDDEEFF",
        )

        mac_bytes = device.mac_bytes

        assert mac_bytes == bytes.fromhex("AABBCCDDEEFF")
        assert len(mac_bytes) == 6

    def test_mac_formatted(self):
        """Test mac_formatted property."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="AABBCCDDEEFF",
        )

        formatted = device.mac_formatted

        assert formatted == "AA:BB:CC:DD:EE:FF"

    def test_get_device_info(self):
        """Test get_device_info method."""
        device = ShellyDevice(
            device_id="my-device",
            device_name="My Device",
            mac_address="112233445566",
        )

        info = device.get_device_info()

        assert info["id"] == "my-device"
        assert info["mac"] == "112233445566"
        assert info["model"] == "SPEM-003CEBEU"
        assert info["gen"] == 2
        assert info["app"] == "Pro3EM"
        assert info["auth_en"] is False
        assert info["auth_domain"] is None

    def test_get_uptime(self):
        """Test get_uptime method returns actual elapsed time."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="AABBCCDDEEFF",
        )

        uptime = device.get_uptime()

        assert uptime >= 0
        assert isinstance(uptime, int)

    def test_get_current_time(self):
        """Test get_current_time method."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="AABBCCDDEEFF",
        )

        current_time = device.get_current_time()

        # Should be close to now
        assert abs(current_time - time.time()) < 1.0
        assert isinstance(current_time, float)

    def test_custom_model_and_versions(self):
        """Test custom model and version values."""
        device = ShellyDevice(
            device_id="test",
            device_name="Test",
            mac_address="AABBCCDDEEFF",
            model="CUSTOM-MODEL",
            firmware_version="2.0.0",
            hardware_version="2.0",
        )

        assert device.model == "CUSTOM-MODEL"
        assert device.firmware_version == "2.0.0"
        assert device.hardware_version == "2.0"

        info = device.get_device_info()
        assert info["ver"] == "2.0.0"
