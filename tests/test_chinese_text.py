import ast
import re
from pathlib import Path

from typer.testing import CliRunner

from lh_quant.cli import app

SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "lh_quant"
HAS_CHINESE = re.compile(r"[\u4e00-\u9fff]")


def test_source_docstrings_are_chinese() -> None:
    missing_or_english: list[str] = []

    for path in SRC_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_docstring = ast.get_docstring(tree)
        if not module_docstring or not HAS_CHINESE.search(module_docstring):
            missing_or_english.append(f"{path.relative_to(SRC_DIR)}:<module>")

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef | ast.FunctionDef):
                docstring = ast.get_docstring(node)
                if not docstring or not HAS_CHINESE.search(docstring):
                    missing_or_english.append(f"{path.relative_to(SRC_DIR)}:{node.name}")

    assert missing_or_english == []


def test_cli_help_text_is_chinese() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["demo-backtest", "--help"])

    assert result.exit_code == 0
    assert "运行入库演示回测" in result.output
    assert "生成多少根交易日K线" in result.output
    assert "用法:" in result.output
    assert "选项" in result.output
    assert "Usage:" not in result.output
    assert "Options" not in result.output
    assert "Show this message and exit" not in result.output
    assert "default:" not in result.output
