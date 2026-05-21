import pandas as pd

from lh_quant.strategies.moving_average import moving_average_cross_signals


def test_moving_average_cross_signals_waits_until_slow_window_exists() -> None:
    bars = pd.DataFrame({"close": [10.0, 11.0, 12.0, 13.0]})

    signals = moving_average_cross_signals(bars, fast_window=2, slow_window=3)

    assert signals.iloc[:2].tolist() == [0, 0]


def test_moving_average_cross_signals_marks_upward_and_downward_crosses() -> None:
    bars = pd.DataFrame(
        {
            "close": [
                10.0,
                10.0,
                10.0,
                12.0,
                14.0,
                12.0,
                10.0,
                8.0,
            ]
        }
    )

    signals = moving_average_cross_signals(bars, fast_window=2, slow_window=3)

    assert 1 in signals.tolist()
    assert -1 in signals.tolist()
