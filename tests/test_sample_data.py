from lh_quant.data.sample import generate_sample_bars
from lh_quant.data.schema import validate_bars


def test_generate_sample_bars_is_deterministic_and_valid() -> None:
    first = generate_sample_bars(symbol="DEMO", periods=32, seed=7)
    second = generate_sample_bars(symbol="DEMO", periods=32, seed=7)

    assert first.equals(second)
    assert len(first) == 32
    assert validate_bars(first).equals(first)

