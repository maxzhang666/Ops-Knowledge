from app.knowledge.chunking.presets import PRESETS, get_strategy_for_preset


def test_all_presets_exist():
    assert len(PRESETS) == 6


def test_get_strategy_for_preset():
    for name in PRESETS:
        strategy, params = get_strategy_for_preset(name)
        assert strategy is not None
        assert "chunk_size" in params


def test_preset_produces_chunks():
    text = "# Title\n\nParagraph one.\n\nParagraph two.\n\n## Section\n\nMore content."
    for name in PRESETS:
        strategy, params = get_strategy_for_preset(name)
        results = strategy.chunk(text, params)
        assert len(results) > 0, f"Preset {name} produced no chunks"
