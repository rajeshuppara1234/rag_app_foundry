import importlib
from unittest.mock import patch
from app.chains.service import RAGService


def test_script_imports_do_not_initialize_remote_clients():
    with (
        patch("azure.ai.projects.AIProjectClient") as client,
        patch("app.retrieval.augument_gen.AugmentGen") as model,
    ):
        for name in ("foundry_client", "foundry_llm", "test_foundry_model"):
            importlib.reload(importlib.import_module(name))
        client.assert_not_called()
        model.assert_not_called()


def test_model_clients_construct_and_close_without_network(settings):
    settings.foundry_api_key = "test"
    settings.azure_openai_api_key = "test"
    # Revalidate to create SecretStr objects after assigning dummy values.
    settings = type(settings)(_env_file=None, **settings.model_dump())
    with patch(
        "httpx.Client.send",
        side_effect=AssertionError("No network during construction"),
    ):
        service = RAGService(settings)
        service.close()


def test_built_frontend_is_served_when_present(api):
    from app.main import STATIC_DIR

    if not (STATIC_DIR / "index.html").exists():
        import pytest

        pytest.skip("Frontend build is verified separately")
    assert api.client.get("/").status_code == 200
    assert api.client.get("/assets/app.js").status_code == 200
    assert api.client.get("/assets/app.css").status_code == 200
    assert "script-src 'self'" in api.client.get("/").headers["content-security-policy"]
