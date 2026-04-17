"""
Unit tests for AIIntegrationService.

Tests cover:
- Service initialization
- Language detection and extraction
- Mods availability checking
- Prompt loading and formatting
- Mods calling
- Debug prompt display
- High-level AI functions (description, summary)
- Singleton pattern
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from inspekt.services.ai_integration import AIIntegrationService, get_ai_service


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_prompts_dir(tmp_path):
    """Create a temporary prompts directory with test prompt files."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    # Create test prompt files
    (prompts_dir / "describe.prompt").write_text("Describe this page structure.")
    (prompts_dir / "summary.prompt").write_text("Summarize this article.")

    return prompts_dir


@pytest.fixture
def service(mock_prompts_dir):
    """Create an AIIntegrationService instance with test prompts."""
    return AIIntegrationService(prompts_dir=mock_prompts_dir)


@pytest.fixture
def reset_singleton():
    """Reset the global singleton between tests."""
    import inspekt.services.ai_integration
    inspekt.services.ai_integration._default_service = None
    yield
    inspekt.services.ai_integration._default_service = None


# =============================================================================
# Test AIIntegrationService Initialization
# =============================================================================


def test_init_with_default_prompts_dir():
    """Test initialization with default prompts_dir (project_root/prompts/)."""
    service = AIIntegrationService()

    # Should resolve to project_root/prompts/
    assert service.prompts_dir.name == "prompts"
    assert service.prompts_dir.parent.name == "zen_bridge"


def test_init_with_custom_prompts_dir(mock_prompts_dir):
    """Test initialization with custom prompts_dir."""
    service = AIIntegrationService(prompts_dir=mock_prompts_dir)

    assert service.prompts_dir == mock_prompts_dir


def test_init_converts_string_to_path(tmp_path):
    """Test that string paths are converted to Path objects."""
    prompts_dir = tmp_path / "custom_prompts"
    prompts_dir.mkdir()

    service = AIIntegrationService(prompts_dir=prompts_dir)

    assert isinstance(service.prompts_dir, Path)
    assert service.prompts_dir == prompts_dir


# =============================================================================
# Test Language Detection - get_target_language
# =============================================================================


def test_get_target_language_with_override(service):
    """Test that language_override takes highest priority."""
    with mock.patch("inspekt.config.load_config", return_value={"ai-language": "nl"}):
        result = service.get_target_language(
            language_override="fr",
            page_lang="en"
        )

        assert result == "fr"


def test_get_target_language_with_config_setting(service):
    """Test language from config when no override provided."""
    with mock.patch("inspekt.config.load_config", return_value={"ai-language": "nl"}):
        result = service.get_target_language(
            language_override=None,
            page_lang="en"
        )

        assert result == "nl"


def test_get_target_language_with_auto_config_and_page_lang(service):
    """Test auto-detection from page_lang when config is 'auto'."""
    with mock.patch("inspekt.config.load_config", return_value={"ai-language": "auto"}):
        result = service.get_target_language(
            language_override=None,
            page_lang="de"
        )

        assert result == "de"


def test_get_target_language_with_auto_config_no_page_lang(service):
    """Test that None is returned when config is 'auto' but no page_lang."""
    with mock.patch("inspekt.config.load_config", return_value={"ai-language": "auto"}):
        result = service.get_target_language(
            language_override=None,
            page_lang=None
        )

        assert result is None


def test_get_target_language_with_defaults(service):
    """Test default behavior returns None (let AI decide)."""
    with mock.patch("inspekt.config.load_config", return_value={}):
        result = service.get_target_language(
            language_override=None,
            page_lang=None
        )

        assert result is None


def test_get_target_language_empty_config_setting(service):
    """Test that empty config setting is treated as 'auto'."""
    with mock.patch("inspekt.config.load_config", return_value={"ai-language": ""}):
        result = service.get_target_language(
            language_override=None,
            page_lang="es"
        )

        assert result == "es"


# =============================================================================
# Test Language Detection - extract_page_language
# =============================================================================


def test_extract_page_language_markdown_pattern(service):
    """Test extracting language from markdown pattern '**Language:** xx'."""
    content = """
    # Page Title

    **Language:** en

    Content here...
    """

    result = service.extract_page_language(content)

    assert result == "en"


def test_extract_page_language_json_pattern(service):
    """Test extracting language from JSON pattern '"lang": "xx"'."""
    content = '{"title": "Test", "lang": "fr", "content": "…"}'

    result = service.extract_page_language(content)

    assert result == "fr"


def test_extract_page_language_markdown_priority_over_json(service):
    """Test that markdown pattern takes priority over JSON."""
    content = '''
    **Language:** nl

    Some content with "lang": "en" in it.
    '''

    result = service.extract_page_language(content)

    assert result == "nl"


def test_extract_page_language_no_match(service):
    """Test that None is returned when no language pattern matches."""
    content = "Just plain text without any language markers."

    result = service.extract_page_language(content)

    assert result is None


def test_extract_page_language_empty_string(service):
    """Test extracting from empty string."""
    result = service.extract_page_language("")

    assert result is None


def test_extract_page_language_with_whitespace_variations(service):
    """Test markdown pattern with different whitespace."""
    content = "**Language:**   de  "

    result = service.extract_page_language(content)

    assert result == "de"


# =============================================================================
# Test Mods Availability Checking
# =============================================================================


def test_check_mods_available_success(service):
    """Test check_mods_available when mods is installed."""
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(returncode=0)

        result = service.check_mods_available()

        assert result is True
        mock_run.assert_called_once_with(
            ["mods", "--version"],
            capture_output=True,
            check=True,
            timeout=5.0,
        )


def test_check_mods_available_not_found(service):
    """Test check_mods_available when mods is not found."""
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        result = service.check_mods_available()

        assert result is False


def test_check_mods_available_timeout(service):
    """Test check_mods_available when command times out."""
    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("mods", 5.0)):
        result = service.check_mods_available()

        assert result is False


def test_check_mods_available_called_process_error(service):
    """Test check_mods_available when mods returns error."""
    with mock.patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "mods")):
        result = service.check_mods_available()

        assert result is False


def test_ensure_mods_available_success(service):
    """Test ensure_mods_available when mods is installed."""
    with mock.patch.object(service, "check_mods_available", return_value=True):
        # Should not raise or exit
        service.ensure_mods_available()


def test_ensure_mods_available_failure(service):
    """Test ensure_mods_available exits when mods is not available."""
    with mock.patch.object(service, "check_mods_available", return_value=False):
        with mock.patch("click.echo") as mock_echo:
            with pytest.raises(SystemExit) as exc_info:
                service.ensure_mods_available()

            assert exc_info.value.code == 1
            assert mock_echo.call_count == 2
            assert "Error: 'mods' command not found" in mock_echo.call_args_list[0][0][0]
            assert "https://github.com/charmbracelet/mods" in mock_echo.call_args_list[1][0][0]


# =============================================================================
# Test Prompt Loading
# =============================================================================


def test_load_prompt_success(service, mock_prompts_dir):
    """Test loading an existing prompt file."""
    result = service.load_prompt("describe.prompt")

    assert result == "Describe this page structure."


def test_load_prompt_strips_whitespace(service, mock_prompts_dir):
    """Test that loaded prompt is stripped of whitespace."""
    (mock_prompts_dir / "test.prompt").write_text("  \n  Test prompt  \n\n  ")

    result = service.load_prompt("test.prompt")

    assert result == "Test prompt"


def test_load_prompt_missing_file(service, mock_prompts_dir):
    """Test load_prompt exits when file doesn't exist."""
    with mock.patch("click.echo") as mock_echo:
        with pytest.raises(SystemExit) as exc_info:
            service.load_prompt("nonexistent.prompt")

        assert exc_info.value.code == 1
        assert "Error: Prompt file not found" in mock_echo.call_args[0][0]


def test_load_prompt_io_error(service, mock_prompts_dir):
    """Test load_prompt exits on IOError."""
    prompt_path = mock_prompts_dir / "error.prompt"
    prompt_path.write_text("content")

    with mock.patch("builtins.open", side_effect=IOError("Permission denied")):
        with mock.patch("click.echo") as mock_echo:
            with pytest.raises(SystemExit) as exc_info:
                service.load_prompt("error.prompt")

            assert exc_info.value.code == 1
            assert "Error reading prompt file" in mock_echo.call_args[0][0]


# =============================================================================
# Test Prompt Formatting
# =============================================================================


def test_format_prompt_base_and_content(service):
    """Test formatting with just base prompt and content."""
    result = service.format_prompt(
        base_prompt="Analyze this:",
        content="Test content"
    )

    expected = "Analyze this:\n\n---\n\nTest content"
    assert result == expected


def test_format_prompt_with_target_lang(service):
    """Test formatting with target language."""
    result = service.format_prompt(
        base_prompt="Analyze this:",
        content="Test content",
        target_lang="fr"
    )

    assert "Analyze this:" in result
    assert "IMPORTANT: Provide your response in fr language." in result
    assert "Test content" in result


def test_format_prompt_with_extra_instructions(service):
    """Test formatting with extra instructions."""
    result = service.format_prompt(
        base_prompt="Analyze this:",
        content="Test content",
        extra_instructions="Be concise."
    )

    assert "Analyze this:" in result
    assert "Be concise." in result
    assert "Test content" in result


def test_format_prompt_with_all_parameters(service):
    """Test formatting with all parameters."""
    result = service.format_prompt(
        base_prompt="Analyze this:",
        content="Test content",
        target_lang="de",
        extra_instructions="Focus on key points."
    )

    assert "Analyze this:" in result
    assert "IMPORTANT: Provide your response in de language." in result
    assert "Focus on key points." in result
    assert "---" in result
    assert "Test content" in result


def test_format_prompt_order(service):
    """Test that prompt parts are in correct order."""
    result = service.format_prompt(
        base_prompt="BASE",
        content="CONTENT",
        target_lang="en",
        extra_instructions="EXTRA"
    )

    parts = result.split("\n\n")
    assert parts[0] == "BASE"
    assert "IMPORTANT" in parts[1]
    assert "EXTRA" in parts[2]
    assert "---" in parts[3]
    assert parts[4] == "CONTENT"


# =============================================================================
# Test Mods Calling
# =============================================================================


def test_call_mods_success(service):
    """Test successful mods call."""
    mock_result = mock.Mock(stdout="AI response here", returncode=0)

    with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
        result = service.call_mods("Test prompt")

        assert result == "AI response here"
        mock_run.assert_called_once_with(
            ["mods"],
            input="Test prompt",
            text=True,
            capture_output=True,
            check=True,
            timeout=60.0,
        )


def test_call_mods_with_timeout_parameter(service):
    """Test call_mods with custom timeout."""
    mock_result = mock.Mock(stdout="Response", returncode=0)

    with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
        service.call_mods("Test", timeout=30.0)

        assert mock_run.call_args[1]["timeout"] == 30.0


def test_call_mods_timeout_expired(service):
    """Test call_mods exits when timeout expires."""
    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("mods", 60.0)):
        with mock.patch("click.echo") as mock_echo:
            with pytest.raises(SystemExit) as exc_info:
                service.call_mods("Test prompt", timeout=60.0)

            assert exc_info.value.code == 1
            assert "Error: mods timed out after 60.0 seconds" in mock_echo.call_args[0][0]


def test_call_mods_called_process_error(service):
    """Test call_mods exits on CalledProcessError."""
    error = subprocess.CalledProcessError(1, "mods", stderr="Error details")

    with mock.patch("subprocess.run", side_effect=error):
        with mock.patch("click.echo") as mock_echo:
            with pytest.raises(SystemExit) as exc_info:
                service.call_mods("Test")

            assert exc_info.value.code == 1
            # Should echo error message and stderr
            assert mock_echo.call_count == 2
            assert "Error calling mods" in mock_echo.call_args_list[0][0][0]


def test_call_mods_with_additional_args(service):
    """Test call_mods with additional CLI arguments."""
    mock_result = mock.Mock(stdout="Response", returncode=0)

    with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
        service.call_mods("Test", additional_args=["--model", "gpt-4"])

        expected_cmd = ["mods", "--model", "gpt-4"]
        assert mock_run.call_args[0][0] == expected_cmd


def test_call_mods_empty_additional_args(service):
    """Test call_mods with empty additional_args list."""
    mock_result = mock.Mock(stdout="Response", returncode=0)

    with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
        service.call_mods("Test", additional_args=[])

        assert mock_run.call_args[0][0] == ["mods"]


# =============================================================================
# Test Debug Prompt Display
# =============================================================================


def test_show_debug_prompt(service):
    """Test debug prompt display formatting."""
    test_prompt = "This is a test prompt\nwith multiple lines"

    with mock.patch("click.echo") as mock_echo:
        service.show_debug_prompt(test_prompt)

        calls = [call[0][0] for call in mock_echo.call_args_list if call[0]]

        # Check for separator lines
        assert "=" * 80 in calls
        # Check for header
        assert any("DEBUG: Full prompt" in str(call) for call in mock_echo.call_args_list)
        # Check prompt is echoed
        assert test_prompt in calls


def test_show_debug_prompt_empty_string(service):
    """Test debug prompt with empty string."""
    with mock.patch("click.echo") as mock_echo:
        service.show_debug_prompt("")

        # Should still display formatting
        assert mock_echo.call_count > 3


# =============================================================================
# Test High-Level AI Functions - generate_description
# =============================================================================


def test_generate_description_success(service):
    """Test successful description generation."""
    page_structure = "**Language:** en\n\nPage content"

    with mock.patch.object(service, "load_prompt", return_value="Base prompt"):
        with mock.patch.object(service, "call_mods", return_value="Generated description"):
            with mock.patch("click.echo"):
                result = service.generate_description(page_structure)

    assert result == "Generated description"


def test_generate_description_with_language_override(service):
    """Test description generation with language override."""
    page_structure = "**Language:** en\n\nContent"

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "format_prompt") as mock_format:
            with mock.patch.object(service, "call_mods", return_value="Description"):
                with mock.patch("click.echo"):
                    service.generate_description(
                        page_structure,
                        language_override="fr"
                    )

    # Check that format_prompt was called with correct target_lang
    call_kwargs = mock_format.call_args[1]
    assert call_kwargs["target_lang"] == "fr"


def test_generate_description_with_debug_mode(service):
    """Test description generation in debug mode."""
    page_structure = "Content"

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "show_debug_prompt") as mock_debug:
            with mock.patch.object(service, "call_mods") as mock_call:
                result = service.generate_description(
                    page_structure,
                    debug=True
                )

    assert result is None
    mock_debug.assert_called_once()
    mock_call.assert_not_called()


def test_generate_description_extracts_page_language(service):
    """Test that generate_description extracts language from content."""
    page_structure = "**Language:** nl\n\nDutch content"

    with mock.patch("inspekt.config.load_config", return_value={"ai-language": "auto"}):
        with mock.patch.object(service, "load_prompt", return_value="Base"):
            with mock.patch.object(service, "format_prompt") as mock_format:
                with mock.patch.object(service, "call_mods", return_value="Desc"):
                    with mock.patch("click.echo"):
                        service.generate_description(page_structure)

    # Should use extracted language 'nl'
    call_kwargs = mock_format.call_args[1]
    assert call_kwargs["target_lang"] == "nl"


def test_generate_description_formats_content_correctly(service):
    """Test that description formats content with PAGE STRUCTURE label."""
    page_structure = "Test content"

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "format_prompt") as mock_format:
            with mock.patch.object(service, "call_mods", return_value="Desc"):
                with mock.patch("click.echo"):
                    service.generate_description(page_structure)

    call_kwargs = mock_format.call_args[1]
    assert "PAGE STRUCTURE:" in call_kwargs["content"]
    assert "Test content" in call_kwargs["content"]


# =============================================================================
# Test High-Level AI Functions - generate_summary
# =============================================================================


def test_generate_summary_success(service):
    """Test successful summary generation."""
    article = {
        "title": "Test Article",
        "content": "Article content here",
        "lang": "en"
    }

    with mock.patch.object(service, "load_prompt", return_value="Base prompt"):
        with mock.patch.object(service, "call_mods", return_value="Generated summary"):
            with mock.patch("click.echo"):
                result = service.generate_summary(article)

    assert result == "Generated summary"


def test_generate_summary_with_language_override(service):
    """Test summary generation with language override."""
    article = {
        "title": "Article",
        "content": "Content",
        "lang": "en"
    }

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "format_prompt") as mock_format:
            with mock.patch.object(service, "call_mods", return_value="Summary"):
                with mock.patch("click.echo"):
                    service.generate_summary(
                        article,
                        language_override="de"
                    )

    call_kwargs = mock_format.call_args[1]
    assert call_kwargs["target_lang"] == "de"


def test_generate_summary_with_debug_mode(service):
    """Test summary generation in debug mode."""
    article = {
        "title": "Test",
        "content": "Content"
    }

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "show_debug_prompt") as mock_debug:
            with mock.patch.object(service, "call_mods") as mock_call:
                result = service.generate_summary(article, debug=True)

    assert result is None
    mock_debug.assert_called_once()
    mock_call.assert_not_called()


def test_generate_summary_uses_article_language(service):
    """Test that summary uses language from article data."""
    article = {
        "title": "Article",
        "content": "Content",
        "lang": "fr"
    }

    with mock.patch("inspekt.config.load_config", return_value={"ai-language": "auto"}):
        with mock.patch.object(service, "load_prompt", return_value="Base"):
            with mock.patch.object(service, "format_prompt") as mock_format:
                with mock.patch.object(service, "call_mods", return_value="Summary"):
                    with mock.patch("click.echo"):
                        service.generate_summary(article)

    call_kwargs = mock_format.call_args[1]
    assert call_kwargs["target_lang"] == "fr"


def test_generate_summary_handles_missing_fields(service):
    """Test summary generation with missing article fields."""
    article = {}  # Missing all fields

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "format_prompt") as mock_format:
            with mock.patch.object(service, "call_mods", return_value="Summary"):
                with mock.patch("click.echo"):
                    service.generate_summary(article)

    call_kwargs = mock_format.call_args[1]
    # Should use default "Untitled" for title
    assert "Untitled" in call_kwargs["content"]


def test_generate_summary_formats_content_with_title(service):
    """Test that summary formats content with title."""
    article = {
        "title": "My Article",
        "content": "The content"
    }

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "format_prompt") as mock_format:
            with mock.patch.object(service, "call_mods", return_value="Summary"):
                with mock.patch("click.echo"):
                    service.generate_summary(article)

    call_kwargs = mock_format.call_args[1]
    assert "Title: My Article" in call_kwargs["content"]
    assert "The content" in call_kwargs["content"]


def test_generate_summary_displays_progress_message(service):
    """Test that summary displays progress message with title."""
    article = {
        "title": "Important Article",
        "content": "Content"
    }

    with mock.patch.object(service, "load_prompt", return_value="Base"):
        with mock.patch.object(service, "call_mods", return_value="Summary"):
            with mock.patch("click.echo") as mock_echo:
                service.generate_summary(article)

    # Find the progress message call
    progress_calls = [
        call for call in mock_echo.call_args_list
        if "Generating summary" in str(call)
    ]
    assert len(progress_calls) == 1
    assert "Important Article" in str(progress_calls[0])


# =============================================================================
# Test Singleton Pattern
# =============================================================================


def test_get_ai_service_returns_singleton(reset_singleton):
    """Test that get_ai_service returns the same instance."""
    service1 = get_ai_service()
    service2 = get_ai_service()

    assert service1 is service2


def test_get_ai_service_with_custom_prompts_dir(reset_singleton, tmp_path):
    """Test get_ai_service with custom prompts_dir."""
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()

    service = get_ai_service(prompts_dir=custom_dir)

    assert service.prompts_dir == custom_dir


def test_get_ai_service_initializes_once(reset_singleton):
    """Test that singleton is only initialized once."""
    with mock.patch("inspekt.services.ai_integration.AIIntegrationService") as mock_class:
        mock_instance = mock.Mock()
        mock_class.return_value = mock_instance

        service1 = get_ai_service()
        service2 = get_ai_service()

        # Constructor should only be called once
        mock_class.assert_called_once()
        assert service1 is service2


def test_get_ai_service_default_initialization(reset_singleton):
    """Test default initialization of singleton."""
    service = get_ai_service()

    assert isinstance(service, AIIntegrationService)
    assert service.prompts_dir is not None
