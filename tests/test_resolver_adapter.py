from pathlib import Path

import controller.resolver_adapter as cra
import toolrunner.app as tapp
import httpx


def test_resolve_context_cwd_matches_toolrunner_workspace(monkeypatch):
    tr_workspace = str(Path(tapp._config.get("paths", {}).get("workspace", "../workspace")).resolve())
    captured = {}

    class DummyClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def post(self, url, json):
            captured["payload"] = json
            class DummyResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {}
            return DummyResp()

    monkeypatch.setattr(cra.httpx, "Client", DummyClient)

    adapter = cra.ResolverAdapter(
        base_url="http://resolver",
        whitelist=[],
        workspace_root=tr_workspace,
    )
    adapter.resolve("hi")

    assert captured["payload"]["context"]["cwd"] == tr_workspace


def test_resolve_returns_none_on_http_error(monkeypatch):
    class DummyClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def post(self, url, json):
            raise httpx.RequestError("boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(cra.httpx, "Client", DummyClient)
    adapter = cra.ResolverAdapter(base_url="http://resolver", whitelist=[], workspace_root=".")
    assert adapter.resolve("hi") is None
