import pandas as pd

from lh_quant.data.akshare_provider import (
    download_akshare_bars,
    normalize_akshare_stock_hist,
    normalize_akshare_stock_hist_tx,
)


def test_normalize_akshare_stock_hist_maps_chinese_columns_to_bar_contract() -> None:
    raw = pd.DataFrame(
        {
            "日期": ["2024-01-02", "2024-01-03"],
            "开盘": [9.90, 10.10],
            "收盘": [10.20, 10.40],
            "最高": [10.30, 10.50],
            "最低": [9.80, 10.00],
            "成交量": [120000, 150000],
        }
    )

    bars = normalize_akshare_stock_hist(raw, symbol="000001")

    assert list(bars.columns) == ["symbol", "datetime", "open", "high", "low", "close", "volume"]
    assert bars["symbol"].tolist() == ["000001", "000001"]
    assert bars["close"].tolist() == [10.20, 10.40]
    assert str(bars["datetime"].dtype).startswith("datetime64")


def test_download_akshare_bars_calls_stock_zh_a_hist_with_yyyymmdd_dates() -> None:
    class FakeAkShare:
        def stock_zh_a_hist(
            self,
            symbol: str,
            period: str,
            start_date: str,
            end_date: str,
            adjust: str,
            timeout: float,
        ) -> pd.DataFrame:
            assert symbol == "000001"
            assert period == "daily"
            assert start_date == "20240101"
            assert end_date == "20240131"
            assert adjust == "qfq"
            assert timeout == 15
            return pd.DataFrame(
                {
                    "日期": ["2024-01-02"],
                    "开盘": [9.90],
                    "收盘": [10.20],
                    "最高": [10.30],
                    "最低": [9.80],
                    "成交量": [120000],
                }
            )

    bars = download_akshare_bars(
        symbol="000001",
        start="2024-01-01",
        end="2024-01-31",
        adjust="qfq",
        akshare_module=FakeAkShare(),
    )

    assert len(bars) == 1
    assert bars.loc[0, "symbol"] == "000001"
    assert bars.attrs["source_detail"] == "AKShare 东方财富日线接口"


def test_normalize_akshare_stock_hist_tx_maps_tencent_columns_to_bar_contract() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "open": [7.83],
            "close": [7.65],
            "high": [7.86],
            "low": [7.65],
            "amount": [1158366.0],
        }
    )

    bars = normalize_akshare_stock_hist_tx(raw, symbol="000001")

    assert bars.loc[0, "symbol"] == "000001"
    assert bars.loc[0, "close"] == 7.65
    assert bars.loc[0, "volume"] == 115836600.0


def test_download_akshare_bars_falls_back_to_tencent_endpoint_when_eastmoney_times_out() -> None:
    class FakeAkShare:
        def stock_zh_a_hist(
            self,
            symbol: str,
            period: str,
            start_date: str,
            end_date: str,
            adjust: str,
            timeout: float,
        ) -> pd.DataFrame:
            raise TimeoutError("东方财富接口超时")

        def stock_zh_a_hist_tx(
            self,
            symbol: str,
            start_date: str,
            end_date: str,
            adjust: str,
            timeout: float,
        ) -> pd.DataFrame:
            assert symbol == "sz000001"
            assert start_date == "20240101"
            assert end_date == "20240131"
            assert adjust == "qfq"
            assert timeout == 15
            return pd.DataFrame(
                {
                    "date": ["2024-01-02"],
                    "open": [7.83],
                    "close": [7.65],
                    "high": [7.86],
                    "low": [7.65],
                    "amount": [1158366.0],
                }
            )

    bars = download_akshare_bars(
        symbol="000001",
        start="2024-01-01",
        end="2024-01-31",
        adjust="qfq",
        akshare_module=FakeAkShare(),
    )

    assert bars.loc[0, "close"] == 7.65
    assert bars.attrs["source_detail"] == "AKShare 腾讯日线接口"
