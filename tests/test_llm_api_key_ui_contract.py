from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_llm_api_key_ui_is_write_only() -> None:
    page = (
        ROOT / "ui_react" / "src" / "pages" / "line_management" / "LlmConfigurationPage.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT / "ui_react" / "src" / "api" / "system" / "llm_configuration_client.ts"
    ).read_text(encoding="utf-8")

    assert 'type="password"' in page
    assert "setApiKey('')" in page
    assert "fetchLlmApiKeyStatus" in page
    assert "replaceLlmApiKey" in page
    assert "testLlmConnection" in page
    assert "測試 Gemini 連線" in page
    assert 'type="text"' not in page
    assert "showApiKey" not in page
    assert "revealApiKey" not in page

    assert "'/api/v1/system/llm/api-key/status'" in client
    assert "'/api/v1/system/llm/api-key'" in client
    assert "'/api/v1/system/llm/connection-test'" in client
    assert "'/api/v1/system/llm/semantic-test'" in client
    assert "api_key: apiKey" in client
    assert "api_key:" not in client.split("fetchLlmApiKeyStatus", 1)[1].split(
        "replaceLlmApiKey", 1
    )[0]
    connection_test = client.split("testLlmConnection", 1)[1].split("testLlmSemantics", 1)[0]
    assert "api_key" not in connection_test
    semantic_test = client.split("testLlmSemantics", 1)[1]
    assert "api_key" not in semantic_test


def test_real_gemini_semantic_panel_is_registered_in_ai_studio() -> None:
    studio = (
        ROOT / "ui_react" / "src" / "pages" / "line_management" / "AiEventStudio.tsx"
    ).read_text(encoding="utf-8")
    panel = (
        ROOT
        / "ui_react"
        / "src"
        / "pages"
        / "line_management"
        / "RealLlmSemanticTestPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "RealLlmSemanticTestPanel" in studio
    assert "Gemini + Knowledge 真實 M2 智能問答工作台" in panel
    assert "testLlmSemantics" in panel
    assert "執行真實 AI 智能解答" in panel
    assert "通報專人客服" in panel
    assert "matched QA" in panel


def test_llm_settings_page_is_registered_in_line_navigation_and_app() -> None:
    layout = (ROOT / "ui_react" / "src" / "components" / "MasterLayout.tsx").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "ui_react" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "'line-llm-settings'" in layout
    assert "AI 模型設定" in layout
    assert "LlmConfigurationPage" in app
    assert "currentPage === 'line-llm-settings'" in app
