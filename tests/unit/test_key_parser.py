"""
Unit tests for the key parser module.
"""

import pytest

from inspekt.services.key_parser import (
    DEFAULT_WAIT_SECONDS,
    MAX_REPEAT_COUNT,
    MAX_WAIT_SECONDS,
    KeySpec,
    expand_repeats,
    get_supported_keys,
    parse_key_sequence,
    parse_key_spec,
)


class TestParseKeySpec:
    """Tests for parse_key_spec function."""

    # === Simple Keys ===

    def test_tab_key(self):
        result = parse_key_spec("Tab")
        assert result.type == "key"
        assert result.key == "Tab"
        assert result.code == "Tab"
        assert result.ctrl is False
        assert result.shift is False

    def test_enter_key(self):
        result = parse_key_spec("Enter")
        assert result.key == "Enter"
        assert result.code == "Enter"

    def test_escape_key(self):
        result = parse_key_spec("Escape")
        assert result.key == "Escape"
        assert result.code == "Escape"

    def test_space_key(self):
        result = parse_key_spec("Space")
        assert result.key == " "
        assert result.code == "Space"

    def test_backspace_key(self):
        result = parse_key_spec("Backspace")
        assert result.key == "Backspace"
        assert result.code == "Backspace"

    def test_delete_key(self):
        result = parse_key_spec("Delete")
        assert result.key == "Delete"
        assert result.code == "Delete"

    # === Case Insensitivity ===

    def test_lowercase_tab(self):
        result = parse_key_spec("tab")
        assert result.key == "Tab"
        assert result.code == "Tab"

    def test_uppercase_tab(self):
        result = parse_key_spec("TAB")
        assert result.key == "Tab"
        assert result.code == "Tab"

    def test_mixed_case_enter(self):
        result = parse_key_spec("eNtEr")
        assert result.key == "Enter"

    # === Key Aliases ===

    def test_esc_alias(self):
        result = parse_key_spec("Esc")
        assert result.key == "Escape"

    def test_return_alias(self):
        result = parse_key_spec("Return")
        assert result.key == "Enter"

    def test_del_alias(self):
        result = parse_key_spec("Del")
        assert result.key == "Delete"

    # === Arrow Keys ===

    def test_arrow_up(self):
        result = parse_key_spec("ArrowUp")
        assert result.key == "ArrowUp"
        assert result.code == "ArrowUp"

    def test_arrow_down(self):
        result = parse_key_spec("ArrowDown")
        assert result.key == "ArrowDown"

    def test_up_alias(self):
        result = parse_key_spec("Up")
        assert result.key == "ArrowUp"

    def test_down_alias(self):
        result = parse_key_spec("Down")
        assert result.key == "ArrowDown"

    def test_left_alias(self):
        result = parse_key_spec("Left")
        assert result.key == "ArrowLeft"

    def test_right_alias(self):
        result = parse_key_spec("Right")
        assert result.key == "ArrowRight"

    # === Page Navigation Keys ===

    def test_home_key(self):
        result = parse_key_spec("Home")
        assert result.key == "Home"

    def test_end_key(self):
        result = parse_key_spec("End")
        assert result.key == "End"

    def test_pageup(self):
        result = parse_key_spec("PageUp")
        assert result.key == "PageUp"

    def test_pgup_alias(self):
        result = parse_key_spec("PgUp")
        assert result.key == "PageUp"

    def test_pagedown(self):
        result = parse_key_spec("PageDown")
        assert result.key == "PageDown"

    def test_pgdown_alias(self):
        result = parse_key_spec("PgDown")
        assert result.key == "PageDown"

    # === Function Keys ===

    def test_f1(self):
        result = parse_key_spec("F1")
        assert result.key == "F1"
        assert result.code == "F1"

    def test_f12(self):
        result = parse_key_spec("F12")
        assert result.key == "F12"
        assert result.code == "F12"

    def test_f5_lowercase(self):
        result = parse_key_spec("f5")
        assert result.key == "F5"

    # === Modifier Combinations ===

    def test_ctrl_a(self):
        result = parse_key_spec("Ctrl+A")
        assert result.type == "key"
        assert result.key == "a"
        assert result.code == "KeyA"
        assert result.ctrl is True
        assert result.alt is False
        assert result.shift is False
        assert result.meta is False

    def test_ctrl_lowercase(self):
        result = parse_key_spec("ctrl+a")
        assert result.ctrl is True
        assert result.key == "a"

    def test_control_alias(self):
        result = parse_key_spec("Control+C")
        assert result.ctrl is True
        assert result.key == "c"

    def test_shift_tab(self):
        result = parse_key_spec("Shift+Tab")
        assert result.shift is True
        assert result.key == "Tab"
        assert result.code == "Tab"

    def test_alt_f4(self):
        result = parse_key_spec("Alt+F4")
        assert result.alt is True
        assert result.key == "F4"

    def test_cmd_c(self):
        result = parse_key_spec("Cmd+C")
        assert result.meta is True
        assert result.key == "c"

    def test_command_alias(self):
        result = parse_key_spec("Command+V")
        assert result.meta is True
        assert result.key == "v"

    def test_meta_key(self):
        result = parse_key_spec("Meta+A")
        assert result.meta is True
        assert result.key == "a"

    def test_win_key(self):
        result = parse_key_spec("Win+E")
        assert result.meta is True
        assert result.key == "e"

    def test_option_alias(self):
        """macOS Option key is Alt."""
        result = parse_key_spec("Option+A")
        assert result.alt is True
        assert result.key == "a"

    def test_multiple_modifiers(self):
        result = parse_key_spec("Ctrl+Shift+A")
        assert result.ctrl is True
        assert result.shift is True
        assert result.alt is False
        assert result.meta is False
        assert result.key == "a"

    def test_all_modifiers(self):
        result = parse_key_spec("Ctrl+Alt+Shift+Meta+X")
        assert result.ctrl is True
        assert result.alt is True
        assert result.shift is True
        assert result.meta is True
        assert result.key == "x"

    # === Single Characters ===

    def test_single_letter(self):
        result = parse_key_spec("a")
        assert result.key == "a"
        assert result.code == "KeyA"

    def test_single_letter_uppercase(self):
        result = parse_key_spec("A")
        assert result.key == "a"
        assert result.code == "KeyA"

    def test_single_digit(self):
        result = parse_key_spec("5")
        assert result.key == "5"
        assert result.code == "Digit5"

    def test_punctuation(self):
        result = parse_key_spec(".")
        assert result.key == "."
        assert result.code == ""  # Varies by layout

    # === Wait Tokens ===

    def test_wait_default(self):
        result = parse_key_spec("Wait")
        assert result.type == "wait"
        assert result.wait_seconds == DEFAULT_WAIT_SECONDS
        assert result.key is None

    def test_wait_lowercase(self):
        result = parse_key_spec("wait")
        assert result.type == "wait"
        assert result.wait_seconds == DEFAULT_WAIT_SECONDS

    def test_wait_custom_integer(self):
        result = parse_key_spec("Wait(3)")
        assert result.type == "wait"
        assert result.wait_seconds == 3.0

    def test_wait_custom_float(self):
        result = parse_key_spec("Wait(1.5)")
        assert result.type == "wait"
        assert result.wait_seconds == 1.5

    def test_wait_small_value(self):
        result = parse_key_spec("Wait(0.1)")
        assert result.wait_seconds == 0.1

    def test_wait_max_allowed(self):
        result = parse_key_spec(f"Wait({MAX_WAIT_SECONDS})")
        assert result.wait_seconds == MAX_WAIT_SECONDS

    def test_wait_exceeds_max(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            parse_key_spec("Wait(120)")

    def test_wait_exceeds_max_message(self):
        with pytest.raises(ValueError, match=str(MAX_WAIT_SECONDS)):
            parse_key_spec("Wait(100)")

    # === Error Cases ===

    def test_empty_string(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_key_spec("")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="Empty"):
            parse_key_spec("   ")

    def test_unknown_key(self):
        with pytest.raises(ValueError, match="Unknown key"):
            parse_key_spec("NotAKey")

    def test_unknown_key_with_suggestions(self):
        """Unknown key similar to a real key should suggest alternatives."""
        with pytest.raises(ValueError, match="Did you mean"):
            parse_key_spec("Tabulator")

    def test_multiple_non_modifier_keys(self):
        with pytest.raises(ValueError, match="Multiple non-modifier"):
            parse_key_spec("Tab+Enter")

    def test_only_modifier(self):
        with pytest.raises(ValueError, match="No key specified"):
            parse_key_spec("Ctrl")

    def test_only_modifiers(self):
        with pytest.raises(ValueError, match="No key specified"):
            parse_key_spec("Ctrl+Shift")

    # === to_dict Method ===

    def test_to_dict_key(self):
        spec = parse_key_spec("Ctrl+A")
        d = spec.to_dict()
        assert d["type"] == "key"
        assert d["key"] == "a"
        assert d["code"] == "KeyA"
        assert d["ctrl"] is True
        assert d["alt"] is False
        assert d["wait_seconds"] is None

    def test_to_dict_wait(self):
        spec = parse_key_spec("Wait(2)")
        d = spec.to_dict()
        assert d["type"] == "wait"
        assert d["wait_seconds"] == 2.0
        assert d["key"] is None


class TestParseKeySequence:
    """Tests for parse_key_sequence function."""

    def test_empty_sequence(self):
        result = parse_key_sequence([])
        assert result == []

    def test_single_key(self):
        result = parse_key_sequence(["Tab"])
        assert len(result) == 1
        assert result[0].key == "Tab"

    def test_multiple_keys(self):
        result = parse_key_sequence(["Tab", "Tab", "Enter"])
        assert len(result) == 3
        assert all(r.type == "key" for r in result)
        assert result[0].key == "Tab"
        assert result[1].key == "Tab"
        assert result[2].key == "Enter"

    def test_with_waits(self):
        result = parse_key_sequence(["Tab", "Wait", "Tab"])
        assert len(result) == 3
        assert result[0].type == "key"
        assert result[1].type == "wait"
        assert result[2].type == "key"

    def test_with_modifiers(self):
        result = parse_key_sequence(["Ctrl+A", "Ctrl+C"])
        assert len(result) == 2
        assert result[0].ctrl is True
        assert result[1].ctrl is True

    def test_mixed_sequence(self):
        result = parse_key_sequence(["Tab", "Wait(1)", "Ctrl+A", "Wait", "Enter"])
        assert len(result) == 5
        assert result[0].key == "Tab"
        assert result[1].wait_seconds == 1.0
        assert result[2].key == "a"
        assert result[2].ctrl is True
        assert result[3].wait_seconds == DEFAULT_WAIT_SECONDS
        assert result[4].key == "Enter"

    def test_invalid_key_in_sequence(self):
        with pytest.raises(ValueError, match="position 2"):
            parse_key_sequence(["Tab", "InvalidKey", "Enter"])

    def test_error_position_reporting(self):
        with pytest.raises(ValueError, match="position 3"):
            parse_key_sequence(["Tab", "Enter", "BadKey"])


class TestGetSupportedKeys:
    """Tests for get_supported_keys function."""

    def test_returns_dict(self):
        result = get_supported_keys()
        assert isinstance(result, dict)

    def test_has_expected_categories(self):
        result = get_supported_keys()
        assert "Navigation" in result
        assert "Arrows" in result
        assert "Function" in result
        assert "Modifiers" in result

    def test_navigation_keys(self):
        result = get_supported_keys()
        nav = result["Navigation"]
        assert "Tab" in nav
        assert "Enter" in nav
        assert "Escape" in nav

    def test_function_keys(self):
        result = get_supported_keys()
        funcs = result["Function"]
        assert "F1" in funcs
        assert "F12" in funcs
        assert len(funcs) == 12


class TestExpandRepeats:
    """Tests for expand_repeats function."""

    # === Basic Repeat Syntax ===

    def test_no_repeat_returns_single_element(self):
        result = expand_repeats("Tab")
        assert result == ["Tab"]

    def test_repeat_once(self):
        result = expand_repeats("Tab*1")
        assert result == ["Tab"]

    def test_repeat_three(self):
        result = expand_repeats("Tab*3")
        assert result == ["Tab", "Tab", "Tab"]

    def test_repeat_six(self):
        result = expand_repeats("Tab*6")
        assert len(result) == 6
        assert all(k == "Tab" for k in result)

    # === With Modifiers ===

    def test_modifier_repeat(self):
        result = expand_repeats("Shift+Tab*2")
        assert result == ["Shift+Tab", "Shift+Tab"]

    def test_complex_modifier_repeat(self):
        result = expand_repeats("Ctrl+Shift+A*3")
        assert result == ["Ctrl+Shift+A", "Ctrl+Shift+A", "Ctrl+Shift+A"]

    # === Edge Cases ===

    def test_wait_token_no_repeat(self):
        """Wait tokens without repeat should work normally."""
        result = expand_repeats("Wait")
        assert result == ["Wait"]

    def test_wait_token_with_duration_no_repeat(self):
        result = expand_repeats("Wait(2)")
        assert result == ["Wait(2)"]

    def test_enter_key(self):
        result = expand_repeats("Enter*2")
        assert result == ["Enter", "Enter"]

    def test_arrow_key(self):
        result = expand_repeats("ArrowDown*5")
        assert result == ["ArrowDown"] * 5

    def test_function_key(self):
        result = expand_repeats("F5*2")
        assert result == ["F5", "F5"]

    # === Maximum Repeat ===

    def test_max_repeat_allowed(self):
        result = expand_repeats(f"Tab*{MAX_REPEAT_COUNT}")
        assert len(result) == MAX_REPEAT_COUNT

    def test_repeat_exceeds_max(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            expand_repeats(f"Tab*{MAX_REPEAT_COUNT + 1}")

    def test_repeat_large_number(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            expand_repeats("Tab*1000")

    # === Error Cases ===

    def test_repeat_zero(self):
        with pytest.raises(ValueError, match="at least 1"):
            expand_repeats("Tab*0")

    def test_repeat_negative_looks_like_invalid(self):
        """Tab*-5 won't match the pattern (digits only), so it passes through."""
        # The regex only matches positive digits, so Tab*-5 is not a repeat
        result = expand_repeats("Tab*-5")
        assert result == ["Tab*-5"]  # Passes through as-is, will fail in parse_key_spec

    def test_repeat_non_numeric(self):
        """Tab*abc won't match the pattern, passes through."""
        result = expand_repeats("Tab*abc")
        assert result == ["Tab*abc"]  # Passes through, will fail in parse_key_spec

    def test_repeat_float_not_matched(self):
        """Tab*2.5 won't match (only digits), passes through."""
        result = expand_repeats("Tab*2.5")
        assert result == ["Tab*2.5"]  # Passes through


class TestParseKeySequenceWithRepeats:
    """Tests for parse_key_sequence with repeat syntax."""

    def test_single_repeat(self):
        result = parse_key_sequence(["Tab*3"])
        assert len(result) == 3
        assert all(r.key == "Tab" for r in result)

    def test_repeat_with_enter(self):
        result = parse_key_sequence(["Tab*3", "Enter"])
        assert len(result) == 4
        assert result[0].key == "Tab"
        assert result[1].key == "Tab"
        assert result[2].key == "Tab"
        assert result[3].key == "Enter"

    def test_modifier_repeat_sequence(self):
        result = parse_key_sequence(["Shift+Tab*2", "Enter"])
        assert len(result) == 3
        assert result[0].shift is True
        assert result[0].key == "Tab"
        assert result[1].shift is True
        assert result[1].key == "Tab"
        assert result[2].key == "Enter"

    def test_multiple_repeats(self):
        result = parse_key_sequence(["Tab*2", "ArrowDown*3"])
        assert len(result) == 5
        assert result[0].key == "Tab"
        assert result[1].key == "Tab"
        assert result[2].key == "ArrowDown"
        assert result[3].key == "ArrowDown"
        assert result[4].key == "ArrowDown"

    def test_repeat_with_wait(self):
        result = parse_key_sequence(["Tab*2", "Wait", "Enter"])
        assert len(result) == 4
        assert result[0].type == "key"
        assert result[1].type == "key"
        assert result[2].type == "wait"
        assert result[3].type == "key"

    def test_repeat_with_custom_wait(self):
        result = parse_key_sequence(["Tab*3", "Wait(1.5)", "Enter"])
        assert len(result) == 5
        assert result[3].type == "wait"
        assert result[3].wait_seconds == 1.5

    def test_complex_sequence(self):
        """Test a realistic complex sequence."""
        result = parse_key_sequence(["Tab*5", "Ctrl+A", "Wait(0.5)", "Enter"])
        assert len(result) == 8
        # 5 Tabs + 1 Ctrl+A + 1 Wait + 1 Enter = 8

    def test_invalid_repeat_count_in_sequence(self):
        with pytest.raises(ValueError, match="at least 1"):
            parse_key_sequence(["Tab*0", "Enter"])

    def test_repeat_exceeds_max_in_sequence(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            parse_key_sequence(["Tab*101"])

    def test_invalid_key_after_repeat_expansion(self):
        """Invalid key syntax after repeat should still error."""
        with pytest.raises(ValueError, match="Unknown key"):
            parse_key_sequence(["InvalidKey*3"])
