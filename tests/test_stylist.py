import random

from interaction.stylist import Stylist


def test_say_key_avoids_recent_repeats():
    stylist = Stylist(
        templates={"status.ok": ["вариант один", "вариант два", "вариант три"]},
        history_size=3,
        randomizer=random.Random(1),
    )

    results = [stylist.say_key("status.ok") for _ in range(6)]

    for prev, current in zip(results, results[1:]):
        assert prev != current


def test_say_key_inserts_placeholders():
    stylist = Stylist(templates={"errors.detail": ["Ошибка: {error}"]}, randomizer=random.Random(0))

    rendered = stylist.say_key("errors.detail", error="boom")
    assert rendered == "Ошибка: boom"


def test_say_filters_apply_replacements():
    stylist = Stylist(templates={"voice": ["ну окей, сделаю"]}, randomizer=random.Random(0))

    rendered = stylist.say_key("voice")
    assert rendered.startswith("Принято")
    assert "принято" in rendered.lower()
