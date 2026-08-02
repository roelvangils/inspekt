"""Unit tests for the screen reader simulator.

Tests cover:
- Data file integrity (announcements, keyboard commands, verbosity, known bugs)
- Schema validation (SRWalkParams, SRElementAnnouncement, etc.)
- Handler data loading and script building
- Bug matching logic
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from inspekt.core.schemas.screen_reader import (
    SRAnnounceParams,
    SRElementAnnouncement,
    SRWalkParams,
    SRWalkResponse,
    SRWalkSummary,
)

# ── Data directory ────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent.parent / "inspekt" / "data" / "screen-reader-rules"


# ── Data File Integrity Tests ─────────────────────────────────


class TestDataFiles:
    """Verify data files are valid and complete."""

    def test_announcements_file_exists(self):
        assert (DATA_DIR / "announcements.json").exists()

    def test_keyboard_commands_file_exists(self):
        assert (DATA_DIR / "keyboard-commands.json").exists()

    def test_verbosity_levels_file_exists(self):
        assert (DATA_DIR / "verbosity-levels.json").exists()

    def test_known_bugs_file_exists(self):
        assert (DATA_DIR / "known-bugs.json").exists()

    def test_all_data_files_are_valid_json(self):
        for filename in [
            "announcements.json",
            "keyboard-commands.json",
            "verbosity-levels.json",
            "known-bugs.json",
        ]:
            path = DATA_DIR / filename
            with open(path) as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{filename} should be a dict"


class TestAnnouncementsData:
    """Verify announcements.json structure and coverage."""

    @pytest.fixture
    def announcements(self):
        with open(DATA_DIR / "announcements.json") as f:
            return json.load(f)

    def test_has_meta(self, announcements):
        assert "_meta" in announcements

    def test_has_at_least_60_roles(self, announcements):
        roles = [k for k in announcements if not k.startswith("_")]
        assert len(roles) >= 60, f"Expected 60+ roles, got {len(roles)}"

    def test_common_roles_present(self, announcements):
        required_roles = [
            "button",
            "link",
            "heading",
            "checkbox",
            "radio",
            "textbox",
            "combobox",
            "list",
            "listitem",
            "img",
            "table",
            "cell",
            "navigation",
            "main",
            "banner",
            "contentinfo",
            "search",
            "dialog",
            "alert",
            "tab",
            "tablist",
            "tabpanel",
            "separator",
            "slider",
            "switch",
            "progressbar",
            "menu",
        ]
        for role in required_roles:
            assert role in announcements, f"Missing role: {role}"

    def test_each_role_has_three_screen_readers(self, announcements):
        for role, data in announcements.items():
            if role.startswith("_"):
                continue
            for sr in ["jaws", "nvda", "voiceover"]:
                assert sr in data, f"Role '{role}' missing screen reader '{sr}'"

    def test_each_role_has_enter_template(self, announcements):
        for role, data in announcements.items():
            if role.startswith("_"):
                continue
            for sr in ["jaws", "nvda", "voiceover"]:
                sr_data = data[sr]
                assert "enter" in sr_data, f"Role '{role}'.{sr} missing 'enter' template"

    def test_heading_templates_use_level(self, announcements):
        for sr in ["jaws", "nvda", "voiceover"]:
            template = announcements["heading"][sr]["enter"]
            assert "{level}" in template, f"Heading template for {sr} should use {{level}}"
            assert "{name}" in template, f"Heading template for {sr} should use {{name}}"

    def test_checkbox_has_states(self, announcements):
        assert "_states" in announcements["checkbox"]
        assert "checked" in announcements["checkbox"]["_states"]
        states = announcements["checkbox"]["_states"]["checked"]
        assert "true" in states
        assert "false" in states
        assert "mixed" in states

    def test_voiceover_uses_different_wording(self, announcements):
        """VoiceOver should use 'tick box' not 'checkbox'."""
        vo_checkbox = announcements["checkbox"]["voiceover"]["enter"]
        assert "tick box" in vo_checkbox

    def test_voiceover_puts_role_after_name_for_links(self, announcements):
        """VoiceOver says 'Name, link' not 'Link, name'."""
        vo_link = announcements["link"]["voiceover"]["enter"]
        assert vo_link.index("{name}") < vo_link.index("link")

    def test_jaws_puts_role_before_name_for_links(self, announcements):
        """JAWS says 'Link, name'."""
        jaws_link = announcements["link"]["jaws"]["enter"]
        assert jaws_link.index("Link") < jaws_link.index("{name}")

    def test_landmarks_have_exit_templates(self, announcements):
        """Landmarks should have exit announcements (at least for JAWS and NVDA)."""
        landmarks = ["banner", "main", "navigation", "contentinfo", "complementary", "search"]
        for landmark in landmarks:
            for sr in ["jaws", "nvda"]:
                assert "exit" in announcements[landmark][sr], (
                    f"Landmark '{landmark}'.{sr} missing 'exit' template"
                )

    def test_global_states_present(self, announcements):
        assert "_global_states" in announcements
        gs = announcements["_global_states"]
        assert "aria-disabled" in gs
        assert "aria-current" in gs
        assert "aria-haspopup" in gs


class TestKeyboardCommandsData:
    """Verify keyboard-commands.json structure."""

    @pytest.fixture
    def commands(self):
        with open(DATA_DIR / "keyboard-commands.json") as f:
            return json.load(f)

    def test_has_three_screen_readers(self, commands):
        for sr in ["jaws", "nvda", "voiceover"]:
            assert sr in commands, f"Missing screen reader: {sr}"

    def test_each_sr_has_info(self, commands):
        for sr in ["jaws", "nvda", "voiceover"]:
            assert "_info" in commands[sr], f"{sr} missing '_info'"
            assert "name" in commands[sr]["_info"]
            assert "modifier" in commands[sr]["_info"]
            assert "modes" in commands[sr]["_info"]

    def test_jaws_has_reading_and_interaction_modes(self, commands):
        assert "reading" in commands["jaws"]
        assert "interaction" in commands["jaws"]

    def test_nvda_has_browse_and_focus_modes(self, commands):
        assert "browse" in commands["nvda"]
        assert "focus" in commands["nvda"]

    def test_voiceover_has_reading_mode(self, commands):
        assert "reading" in commands["voiceover"]

    def test_heading_navigation_present(self, commands):
        """All SRs should have a 'next heading' shortcut."""
        assert "h" in commands["jaws"]["reading"]["quick_nav"]
        assert "h" in commands["nvda"]["browse"]["quick_nav"]
        assert "VO+Cmd+h" in commands["voiceover"]["reading"]["quick_nav"]

    def test_cheat_sheet_templates_present(self, commands):
        assert "_cheat_sheet_templates" in commands
        for sr in ["jaws", "nvda", "voiceover"]:
            assert sr in commands["_cheat_sheet_templates"]

    def test_cheat_sheet_has_navigate_and_actions(self, commands):
        for sr in ["jaws", "nvda", "voiceover"]:
            sheets = commands["_cheat_sheet_templates"][sr]
            assert "Navigate" in sheets, f"{sr} cheat sheet missing 'Navigate'"
            assert "Actions" in sheets, f"{sr} cheat sheet missing 'Actions'"


class TestVerbosityData:
    """Verify verbosity-levels.json structure."""

    @pytest.fixture
    def verbosity(self):
        with open(DATA_DIR / "verbosity-levels.json") as f:
            return json.load(f)

    def test_has_three_levels(self, verbosity):
        for level in ["high", "medium", "low"]:
            assert level in verbosity, f"Missing level: {level}"

    def test_high_enables_everything(self, verbosity):
        high = verbosity["high"]
        for key, value in high.items():
            if key.startswith("_"):
                continue
            assert value is True, f"High verbosity should enable '{key}'"

    def test_low_disables_optional_features(self, verbosity):
        low = verbosity["low"]
        assert low["announce_description"] is False
        assert low["announce_hints"] is False
        assert low["announce_position_in_set"] is False
        assert low["announce_landmarks_on_enter"] is False

    def test_all_levels_have_same_keys(self, verbosity):
        high_keys = set(k for k in verbosity["high"] if not k.startswith("_"))
        medium_keys = set(k for k in verbosity["medium"] if not k.startswith("_"))
        low_keys = set(k for k in verbosity["low"] if not k.startswith("_"))
        assert high_keys == medium_keys == low_keys


class TestKnownBugsData:
    """Verify known-bugs.json structure."""

    @pytest.fixture
    def bugs_data(self):
        with open(DATA_DIR / "known-bugs.json") as f:
            return json.load(f)

    def test_has_bugs_array(self, bugs_data):
        assert "bugs" in bugs_data
        assert isinstance(bugs_data["bugs"], list)
        assert len(bugs_data["bugs"]) > 0

    def test_each_bug_has_required_fields(self, bugs_data):
        required = ["id", "screen_reader", "severity", "description"]
        for bug in bugs_data["bugs"]:
            for field in required:
                assert field in bug, f"Bug '{bug.get('id', '?')}' missing field '{field}'"

    def test_each_bug_has_role_or_property(self, bugs_data):
        for bug in bugs_data["bugs"]:
            has_role = "role" in bug
            has_property = "property" in bug
            assert has_role or has_property, f"Bug '{bug['id']}' needs either 'role' or 'property'"

    def test_valid_severity_values(self, bugs_data):
        valid = {"critical", "serious", "moderate", "minor"}
        for bug in bugs_data["bugs"]:
            assert bug["severity"] in valid, (
                f"Bug '{bug['id']}' has invalid severity: {bug['severity']}"
            )

    def test_valid_screen_reader_values(self, bugs_data):
        valid = {"jaws", "nvda", "voiceover", "orca", "narrator", "talkback"}
        for bug in bugs_data["bugs"]:
            assert bug["screen_reader"] in valid, (
                f"Bug '{bug['id']}' has invalid SR: {bug['screen_reader']}"
            )

    def test_unique_bug_ids(self, bugs_data):
        ids = [bug["id"] for bug in bugs_data["bugs"]]
        assert len(ids) == len(set(ids)), "Bug IDs must be unique"


# ── Schema Tests ──────────────────────────────────────────────


class TestSRWalkParams:
    """Test SRWalkParams schema validation."""

    def test_defaults(self):
        params = SRWalkParams()
        assert params.screen_reader == "all"
        assert params.verbosity == "high"
        assert params.max_elements == 500
        assert params.include_bugs is True

    def test_valid_screen_readers(self):
        for sr in ["jaws", "nvda", "voiceover", "all"]:
            params = SRWalkParams(screen_reader=sr)
            assert params.screen_reader == sr

    def test_invalid_screen_reader(self):
        with pytest.raises(ValidationError):
            SRWalkParams(screen_reader="siri")

    def test_valid_verbosity(self):
        for v in ["high", "medium", "low"]:
            params = SRWalkParams(verbosity=v)
            assert params.verbosity == v

    def test_invalid_verbosity(self):
        with pytest.raises(ValidationError):
            SRWalkParams(verbosity="maximum")


class TestSRElementAnnouncement:
    """Test SRElementAnnouncement schema."""

    def test_minimal_valid(self):
        a = SRElementAnnouncement(index=0, selector="h1", tag="h1", role="heading", name="Title")
        assert a.index == 0
        assert a.is_focusable is False
        assert a.known_bugs == []

    def test_full_enriched(self):
        a = SRElementAnnouncement(
            index=5,
            selector="input#email",
            tag="input",
            role="textbox",
            name="Email",
            jaws="Email, edit, required",
            nvda="Email, edit field, required",
            voiceover="Email, required, text field",
            description="Enter your email address",
            is_focusable=True,
            tab_index=0,
            value="user@example.com",
            placeholder="name@example.com",
            jaws_secondary="Enter your email address",
            nvda_secondary="Enter your email address",
            voiceover_secondary="Help text: Enter your email address",
            known_bugs=["nvda-aria-required-not-announced"],
        )
        assert a.is_focusable is True
        assert len(a.known_bugs) == 1
        assert a.voiceover_secondary.startswith("Help text:")

    def test_table_context(self):
        a = SRElementAnnouncement(
            index=10,
            selector="td",
            tag="td",
            role="cell",
            name="$42.00",
            table_column_header="Price",
            table_row_header="Widget A",
        )
        assert a.table_column_header == "Price"
        assert a.table_row_header == "Widget A"


class TestSRWalkResponse:
    """Test SRWalkResponse schema."""

    def test_successful_response(self):
        resp = SRWalkResponse(
            success=True,
            url="https://example.com",
            title="Example",
            element_count=3,
            announcements=[
                SRElementAnnouncement(
                    index=0,
                    selector="h1",
                    tag="h1",
                    role="heading",
                    name="Welcome",
                    jaws="Heading level 1, Welcome",
                ),
            ],
            summary=SRWalkSummary(total_elements=3, headings=1),
            difference_count=0,
        )
        assert resp.success is True
        assert len(resp.announcements) == 1

    def test_failed_response(self):
        resp = SRWalkResponse(success=False, error="Bridge not connected")
        assert resp.success is False
        assert resp.error == "Bridge not connected"


class TestSRAnnounceParams:
    """Test SRAnnounceParams schema."""

    def test_defaults(self):
        params = SRAnnounceParams()
        assert params.selector is None
        assert params.screen_reader == "all"

    def test_with_selector(self):
        params = SRAnnounceParams(selector="button.submit")
        assert params.selector == "button.submit"


# ── Handler Tests ─────────────────────────────────────────────


class TestHandlerDataLoading:
    """Test handler data loading functions."""

    def test_load_announcements(self):
        from inspekt.core.handlers.screen_reader import _get_announcements

        data = _get_announcements()
        assert "heading" in data
        assert "link" in data
        assert "button" in data

    def test_load_verbosity(self):
        from inspekt.core.handlers.screen_reader import _get_verbosity

        data = _get_verbosity()
        assert "high" in data
        assert "medium" in data
        assert "low" in data

    def test_load_known_bugs(self):
        from inspekt.core.handlers.screen_reader import _get_known_bugs

        data = _get_known_bugs()
        assert "bugs" in data
        assert len(data["bugs"]) > 0

    def test_get_bug_details(self):
        from inspekt.core.handlers.screen_reader import get_bug_details

        bug = get_bug_details("voiceover-alert-no-role")
        assert bug is not None
        assert bug["screen_reader"] == "voiceover"
        assert bug["role"] == "alert"

    def test_get_bug_details_not_found(self):
        from inspekt.core.handlers.screen_reader import get_bug_details

        bug = get_bug_details("nonexistent-bug-id")
        assert bug is None

    def test_build_script_includes_all_data(self):
        from inspekt.core.handlers.screen_reader import _build_sr_script

        config = {"mode": "walk", "screenReader": "all", "verbosity": "high", "maxElements": 10}
        script = _build_sr_script(config)

        # Should not contain any unreplaced placeholders
        assert "__SR_ANNOUNCEMENTS__" not in script
        assert "__SR_VERBOSITY__" not in script
        assert "__SR_KNOWN_BUGS__" not in script
        assert "__SR_CONFIG__" not in script

        # Should contain actual data
        assert '"heading"' in script  # from announcements
        assert '"high"' in script  # from verbosity
        assert '"bugs"' in script  # from known bugs
        assert '"walk"' in script  # from config

    def test_build_script_is_valid_js(self):
        """The built script should be syntactically valid JavaScript."""
        import subprocess

        from inspekt.core.handlers.screen_reader import _build_sr_script

        config = {"mode": "state"}
        script = _build_sr_script(config)

        # Use node to parse-check the script
        result = subprocess.run(
            [
                "node",
                "-e",
                f"try {{ new Function({json.dumps(script)}); console.log('ok'); }} catch(e) {{ console.error(e.message); process.exit(1); }}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"


# ── JS Simulator Syntax Tests ────────────────────────────────


class TestJSSimulatorSyntax:
    """Verify the JS simulator file is syntactically valid."""

    def test_simulator_file_exists(self):
        path = (
            Path(__file__).parent.parent.parent
            / "inspekt"
            / "scripts"
            / "screen_reader_simulator.js"
        )
        assert path.exists()

    def test_simulator_has_required_placeholders(self):
        path = (
            Path(__file__).parent.parent.parent
            / "inspekt"
            / "scripts"
            / "screen_reader_simulator.js"
        )
        content = path.read_text()
        assert "__SR_ANNOUNCEMENTS__" in content
        assert "__SR_VERBOSITY__" in content
        assert "__SR_KNOWN_BUGS__" in content
        assert "__SR_CONFIG__" in content

    def test_simulator_has_key_classes(self):
        path = (
            Path(__file__).parent.parent.parent
            / "inspekt"
            / "scripts"
            / "screen_reader_simulator.js"
        )
        content = path.read_text()
        assert "class AnnouncementEngine" in content
        assert "class VirtualCursor" in content
        assert "class LiveRegionMonitor" in content

    def test_simulator_has_walk_function(self):
        path = (
            Path(__file__).parent.parent.parent
            / "inspekt"
            / "scripts"
            / "screen_reader_simulator.js"
        )
        content = path.read_text()
        assert "function walkPage" in content

    def test_simulator_has_interactive_api(self):
        path = (
            Path(__file__).parent.parent.parent
            / "inspekt"
            / "scripts"
            / "screen_reader_simulator.js"
        )
        content = path.read_text()
        assert "function startSimulator" in content
        assert "function stopSimulator" in content
        assert "function navigate" in content


# ── Command Registration Tests ────────────────────────────────


class TestCommandRegistration:
    """Test that SR commands are properly registered."""

    def test_commands_importable(self):
        from inspekt.core.commands.screen_reader import SCREEN_READER_COMMANDS

        assert len(SCREEN_READER_COMMANDS) == 3  # sr group, sr_walk, sr_announce

    def test_sr_group_is_group(self):
        from inspekt.core.commands.screen_reader import sr

        assert sr.is_group is True

    def test_sr_walk_has_handler(self):
        from inspekt.core.commands.screen_reader import sr_walk

        assert sr_walk.handler is not None
        assert "screen_reader" in sr_walk.handler

    def test_sr_announce_has_handler(self):
        from inspekt.core.commands.screen_reader import sr_announce

        assert sr_announce.handler is not None

    def test_sr_walk_has_mcp_name(self):
        from inspekt.core.commands.screen_reader import sr_walk

        assert sr_walk.mcp_name == "screen_reader_walk"

    def test_sr_walk_category_is_accessibility(self):
        from inspekt.core.commands.base import Category
        from inspekt.core.commands.screen_reader import sr_walk

        assert sr_walk.category == Category.ACCESSIBILITY
