from interaction.resolver.resolver import ResolverConfig, ResolverService


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

