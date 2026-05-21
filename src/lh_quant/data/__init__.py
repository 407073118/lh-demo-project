"""真实数据下载、开发演示数据生成和K线数据校验。"""

from lh_quant.data.akshare_provider import AkShareDataError, download_akshare_bars
from lh_quant.data.sample import generate_sample_bars
from lh_quant.data.schema import BarValidationError, validate_bars
from lh_quant.data.yahoo import YahooDataError, download_yahoo_bars

__all__ = [
    "AkShareDataError",
    "BarValidationError",
    "YahooDataError",
    "download_akshare_bars",
    "download_yahoo_bars",
    "generate_sample_bars",
    "validate_bars",
]
