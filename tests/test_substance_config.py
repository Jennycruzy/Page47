from pathlib import Path

from page47.substance.reader import load_substance_config


def test_live_attachment_reading_configuration_loads() -> None:
    config = load_substance_config(Path("config/substance.yaml"))
    assert config.minimum_references == 1
    assert config.context_characters == 180
    assert len(config.terms) > 0
    assert len(config.references) == 4
