from pathlib import Path


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())


def test_faq_studio_does_not_mount_retired_model_surface() -> None:
    frontend = ROOT / "ui_react" / "src"
    studio = (frontend / "pages" / "line_management" / "LineFaqStudioPage.tsx").read_text(encoding="utf-8")
    app = (frontend / "App.tsx").read_text(encoding="utf-8")
    backend = (ROOT / "api" / "main.py").read_text(encoding="utf-8")

    assert "CommonQaCatalogPanel" in studio and "FaqChatLayoutPanel" in studio
    for retired in ("RealLlmSemanticTestPanel", "KnowledgeFeedbackPanel", "LlmConfigurationPage"):
        assert retired not in studio
    assert "currentPage === 'line-faq'" in app
    assert "llm_configuration.router" not in backend
