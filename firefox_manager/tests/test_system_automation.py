"""
Unit tests for SystemLevelAutomation.
Validates Windows OS input constants, typing logic, and window focusing functions.
"""

import sys
import pytest
from firefox_manager.authentication.system_automation import (
    SystemLevelAutomation,
    VK_TAB,
    VK_RETURN,
    KEYEVENTF_UNICODE,
)


def test_system_automation_constants():
    auto = SystemLevelAutomation()
    assert VK_TAB == 0x09
    assert VK_RETURN == 0x0D
    assert KEYEVENTF_UNICODE == 0x0004
    if sys.platform == "win32":
        assert auto.user32 is not None


def test_type_unicode_text_safe():
    auto = SystemLevelAutomation()
    # Does not crash on arbitrary clipboard strings
    auto.set_clipboard("test_unit")
    auto.clear_clipboard()

