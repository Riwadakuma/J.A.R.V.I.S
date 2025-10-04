from interaction.resolver.resolver import ResolverConfig, ResolverService


class _DummyResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def make_resolver():
    cfg = ResolverConfig(
        whitelist=[
            "files.list",
            "files.read",
            "files.create",
            "files.append",
            "system.help",
            "system.config_set",
        ],
        remote_url=None,
        mode="quick",
    )
    return ResolverService(config=cfg)


def make_remote_resolver(payload):
    cfg = ResolverConfig(
        whitelist=[
            "files.list",
            "files.read",
            "files.create",
            "files.append",
            "system.help",
            "system.config_set",
        ],
        remote_url="http://resolver.local",
        mode="hybrid",
        use_legacy_when_low_conf=False,
    )

    class Client:
        def __init__(self, timeout):
            self._payload = payload
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json):
            return _DummyResponse(self._payload)

    client_cls = Client
    return ResolverService(config=cfg, http_client_cls=client_cls)


def test_quick_rules_strip_quotes():
    resolver = make_resolver()
    intent = resolver.resolve('прочитай файл "notes.txt"', context={})
    assert intent.is_command()
    assert intent.name == "files.read"
    assert intent.args["path"] == "notes.txt"


def test_append_with_content():
    resolver = make_resolver()
    intent = resolver.resolve('допиши в файл story.txt: финал', context={})
    assert intent.is_command()
    assert intent.name == "files.append"
    assert intent.args == {"path": "story.txt", "content": "финал"}


def test_unknown_phrase_returns_chat():
    resolver = make_resolver()
    intent = resolver.resolve("привет", context={})
    assert not intent.is_command()


def test_remote_command_downgraded_when_text_lacks_command_hints():
    resolver = make_remote_resolver(
        {
            "command": "files.list",
            "args": {"mask": "*"},
            "confidence": 0.91,
            "resolver_rule": "remote",
            "explain": ["remote:match"],
        }
    )
    intent = resolver.resolve("что ты умеешь?", context={})
    assert not intent.is_command()
    assert intent.text == "что ты умеешь?"
    assert intent.meta.rule == "remote_suspect_command"
    assert any(part.startswith("ignored_remote_command") for part in intent.meta.explain)


def test_remote_command_kept_when_text_contains_command_hints():
    resolver = make_remote_resolver(
        {
            "command": "files.list",
            "args": {"mask": "*"},
            "confidence": 0.82,
            "resolver_rule": "remote",
            "explain": ["remote:match"],
        }
    )
    phrase = "мне нужно показать файлы проекта"
    intent = resolver.resolve(phrase, context={})
    assert intent.is_command()
    assert intent.name == "files.list"
