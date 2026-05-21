"""数据库连接配置和初始化逻辑。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from lh_quant.storage.schema import metadata

DEFAULT_DATABASE_URL = "mysql+pymysql://root:123456@localhost:3306/lh_quant?charset=utf8mb4"


@dataclass(frozen=True)
class DatabaseStatus:
    """数据库初始化结果，供 API 健康检查和日志展示。"""

    connected: bool
    url: str
    message: str


def get_database_url() -> str:
    """读取数据库连接地址，默认使用本地 MySQL 的 root/123456。"""

    return os.getenv("LH_QUANT_DATABASE_URL", DEFAULT_DATABASE_URL)


def create_database_engine(database_url: str | None = None) -> Engine:
    """创建 SQLAlchemy Engine，并启用连接池预检查。"""

    url = database_url or get_database_url()
    return create_engine(url, pool_pre_ping=True, future=True)


def initialize_database(engine: Engine) -> DatabaseStatus:
    """初始化数据库和表结构；MySQL 数据库不存在时会先创建。"""

    url = engine.url
    if url.get_backend_name() in {"mysql", "mariadb"}:
        _ensure_mysql_database(url)
    metadata.create_all(engine)
    return DatabaseStatus(
        connected=True,
        url=_mask_database_url(str(engine.url)),
        message="数据库已连接",
    )


def initialize_database_safely(engine: Engine) -> DatabaseStatus:
    """初始化数据库，失败时返回中文错误而不是中断 API 启动。"""

    try:
        return initialize_database(engine)
    except Exception as error:
        return DatabaseStatus(
            connected=False,
            url=_mask_database_url(str(engine.url)),
            message=f"数据库连接失败: {error}",
        )


def _ensure_mysql_database(url: URL) -> None:
    """连接 MySQL 服务端并创建项目数据库。"""

    database = url.database
    if not database:
        return

    server_url = _server_url_without_database(url)
    with create_engine(server_url, pool_pre_ping=True, future=True).begin() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )


def _server_url_without_database(url: URL) -> URL:
    """生成连接 MySQL 服务端的 URL，用于在目标数据库不存在时先建库。"""

    return url.set(database="")


def _mask_database_url(database_url: str) -> str:
    """隐藏数据库连接地址里的密码，避免日志和接口泄漏凭据。"""

    try:
        url = make_url(database_url)
    except Exception:
        return database_url
    return str(url.set(password="***")) if url.password else str(url)
