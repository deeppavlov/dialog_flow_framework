"""
Yandex DB
---------
The Yandex DB module provides a version of the :py:class:`.DBContextStorage` class that designed to work with
Yandex and other databases. Yandex DataBase is a fully-managed cloud-native SQL service that makes it easy to set up,
operate, and scale high-performance and high-availability databases for your applications.

The Yandex DB module uses the Yandex Cloud SDK, which is a python library that allows you to work
with Yandex Cloud services using python. This allows the DFF to easily integrate with the Yandex DataBase and
take advantage of the scalability and high-availability features provided by the service.
"""
import asyncio
import datetime
import os
import pickle
from typing import Any, Tuple, List, Dict, Optional
from urllib.parse import urlsplit

from dff.script import Context

from .database import DBContextStorage, cast_key_to_string
from .protocol import get_protocol_install_suggestion
from .context_schema import ExtraFields

try:
    from ydb import (
        SerializableReadWrite,
        SchemeError,
        TableDescription,
        Column,
        OptionalType,
        PrimitiveType,
        TableIndex,
    )
    from ydb.aio import Driver, SessionPool

    ydb_available = True
except ImportError:
    ydb_available = False


class YDBContextStorage(DBContextStorage):
    """
    Version of the :py:class:`.DBContextStorage` for YDB.

    Context value fields are stored in table `contexts`.
    Columns of the table are: active_ctx, primary_id, storage_key, created_at and updated_at.

    Context dictionary fields are stored in tables `TABLE_NAME_PREFIX_FIELD`.
    Columns of the tables are: primary_id, key, value, created_at and updated_at,
    where key contains nested dict key and value contains nested dict value.

    Context reading is done with one query to each table.
    Context reading is done with multiple queries to each table, one for each nested key.

    :param path: Standard sqlalchemy URI string. One of `grpc` or `grpcs` can be chosen as a protocol.
        Example: `grpc://localhost:2134/local`.
        NB! Do not forget to provide credentials in environmental variables
        or set `YDB_ANONYMOUS_CREDENTIALS` variable to `1`!
    :param table_name: The name of the table to use.
    """

    _CONTEXTS_TABLE = "contexts"
    _LOGS_TABLE = "logs"
    _KEY_COLUMN = "key"
    _VALUE_COLUMN = "value"
    _FIELD_COLUMN = "field"
    _PACKED_COLUMN = "data"

    def __init__(self, path: str, table_name_prefix: str = "dff_table", timeout=5):
        DBContextStorage.__init__(self, path)
        protocol, netloc, self.database, _, _ = urlsplit(path)
        self.endpoint = "{}://{}".format(protocol, netloc)
        if not ydb_available:
            install_suggestion = get_protocol_install_suggestion("grpc")
            raise ImportError("`ydb` package is missing.\n" + install_suggestion)

         # TODO: no documentation found, might be larger or not exist at all!
        self._insert_limit = 10000
        self.table_prefix = table_name_prefix
        self.driver, self.pool = asyncio.run(_init_drive(timeout, self.endpoint, self.database, table_name_prefix))

    @cast_key_to_string()
    async def del_item_async(self, key: str):
        async def callee(session):
            query = f"""
                PRAGMA TablePathPrefix("{self.database}");
                DECLARE ${ExtraFields.storage_key.value} AS Utf8;
                UPDATE {self.table_prefix}_{self._CONTEXTS_TABLE} SET {ExtraFields.active_ctx.value}=False
                WHERE {ExtraFields.storage_key.value} == ${ExtraFields.storage_key.value};
                """

            await session.transaction(SerializableReadWrite()).execute(
                await session.prepare(query),
                {f"${ExtraFields.storage_key.value}": key},
                commit_tx=True,
            )

        return await self.pool.retry_operation(callee)

    async def len_async(self) -> int:
        async def callee(session):
            query = f"""
                PRAGMA TablePathPrefix("{self.database}");
                SELECT COUNT(DISTINCT {ExtraFields.storage_key.value}) as cnt
                FROM {self.table_prefix}_{self._CONTEXTS_TABLE}
                WHERE {ExtraFields.active_ctx.value} == True;
                """

            result_sets = await session.transaction(SerializableReadWrite()).execute(
                await session.prepare(query),
                commit_tx=True,
            )
            return result_sets[0].rows[0].cnt if len(result_sets[0].rows) > 0 else 0

        return await self.pool.retry_operation(callee)

    async def clear_async(self):
        async def callee(session):
            query = f"""
                PRAGMA TablePathPrefix("{self.database}");
                UPDATE {self.table_prefix}_{self._CONTEXTS_TABLE} SET {ExtraFields.active_ctx.value}=False;
                """

            await session.transaction(SerializableReadWrite()).execute(
                await session.prepare(query),
                commit_tx=True,
            )

        return await self.pool.retry_operation(callee)

    @cast_key_to_string()
    async def _get_last_ctx(self, key: str) -> Optional[str]:
        async def callee(session):
            query = f"""
                PRAGMA TablePathPrefix("{self.database}");
                DECLARE ${ExtraFields.storage_key.value} AS Utf8;
                SELECT {ExtraFields.primary_id.value}
                FROM {self.table_prefix}_{self._CONTEXTS_TABLE}
                WHERE {ExtraFields.storage_key.value} == ${ExtraFields.storage_key.value} AND {ExtraFields.active_ctx.value} == True
                LIMIT 1;
                """

            result_sets = await session.transaction(SerializableReadWrite()).execute(
                await session.prepare(query),
                {f"${ExtraFields.storage_key.value}": key},
                commit_tx=True,
            )
            return result_sets[0].rows[0][ExtraFields.primary_id.value] if len(result_sets[0].rows) > 0 else None

        return await self.pool.retry_operation(callee)

    async def _read_pac_ctx(self, _: str, primary_id: str) -> Dict:
        async def callee(session):
            query = f"""
                PRAGMA TablePathPrefix("{self.database}");
                DECLARE ${ExtraFields.primary_id.value} AS Utf8;
                SELECT {self._PACKED_COLUMN}
                FROM {self.table_prefix}_{self._CONTEXTS_TABLE}
                WHERE {ExtraFields.primary_id.value} = ${ExtraFields.primary_id.value}
                """
            
            result_sets = await session.transaction(SerializableReadWrite()).execute(
                await session.prepare(query),
                {f"${ExtraFields.primary_id.value}": primary_id},
                commit_tx=True,
            )

            if len(result_sets[0].rows) > 0:
                return pickle.loads(result_sets[0].rows[0][self._PACKED_COLUMN])
            else:
                return dict()

        return await self.pool.retry_operation(callee)

    async def _read_log_ctx(self, keys_limit: Optional[int], keys_offset: int, field_name: str, primary_id: str) -> Dict:
        async def callee(session):
            limit = 1001 if keys_limit is None else keys_limit

            query = f"""
                PRAGMA TablePathPrefix("{self.database}");
                DECLARE ${ExtraFields.primary_id.value} AS Utf8;
                DECLARE ${self._FIELD_COLUMN} AS Utf8;
                SELECT {self._KEY_COLUMN}, {self._VALUE_COLUMN}
                FROM {self.table_prefix}_{self._LOGS_TABLE}
                WHERE {ExtraFields.primary_id.value} = ${ExtraFields.primary_id.value} AND {self._FIELD_COLUMN} = ${self._FIELD_COLUMN}
                ORDER BY {self._KEY_COLUMN} DESC
                LIMIT {limit}
                """

            final_offset = keys_offset
            result_sets = None

            result_dict = dict()
            while result_sets is None or result_sets[0].truncated:
                final_query = f"{query} OFFSET {final_offset};"
                result_sets = await session.transaction(SerializableReadWrite()).execute(
                    await session.prepare(final_query),
                    {f"${ExtraFields.primary_id.value}": primary_id, f"${self._FIELD_COLUMN}": field_name},
                    commit_tx=True,
                )

                if len(result_sets[0].rows) > 0:
                    for key, value in {row[self._KEY_COLUMN]: row[self._VALUE_COLUMN] for row in result_sets[0].rows}.items():
                        result_dict[key] = pickle.loads(value)

                final_offset += 1000

            return result_dict

        return await self.pool.retry_operation(callee)


    async def _write_pac_ctx(self, data: Dict, storage_key: str, primary_id: str):
        async def callee(session):
            request = f"""
                PRAGMA TablePathPrefix("{self.database}");
                DECLARE ${ExtraFields.primary_id.value} AS Utf8;
                SELECT {ExtraFields.created_at.value}
                FROM {self.table_prefix}_{self._CONTEXTS_TABLE}
                WHERE {ExtraFields.primary_id.value} = ${ExtraFields.primary_id.value};
            """

            existing_context = await session.transaction(SerializableReadWrite()).execute(
                await session.prepare(request),
                {f"${ExtraFields.primary_id.value}": primary_id},
                commit_tx=True,
            )

            if len(existing_context[0].rows) > 0:
                created_at = existing_context[0].rows[0][ExtraFields.created_at.value]
            else:
                created_at = datetime.datetime.now()

            query = f"""
                PRAGMA TablePathPrefix("{self.database}");
                DECLARE ${self._PACKED_COLUMN} AS String;
                DECLARE ${ExtraFields.primary_id.value} AS Utf8;
                DECLARE ${ExtraFields.storage_key.value} AS Utf8;
                DECLARE ${ExtraFields.created_at.value} AS Timestamp;
                UPSERT INTO {self.table_prefix}_{self._CONTEXTS_TABLE} ({self._PACKED_COLUMN}, {ExtraFields.storage_key.value}, {ExtraFields.primary_id.value}, {ExtraFields.active_ctx.value}, {ExtraFields.created_at.value}, {ExtraFields.updated_at.value})
                VALUES (${self._PACKED_COLUMN}, ${ExtraFields.storage_key.value}, ${ExtraFields.primary_id.value}, True, ${ExtraFields.created_at.value}, CurrentUtcDatetime());
                """

            await session.transaction(SerializableReadWrite()).execute(
                await session.prepare(query),
                {
                    f"${self._PACKED_COLUMN}": pickle.dumps(data),
                    f"${ExtraFields.primary_id.value}": primary_id,
                    f"${ExtraFields.storage_key.value}": storage_key,
                    f"${ExtraFields.created_at.value}": created_at,
                },
                commit_tx=True,
            )

        return await self.pool.retry_operation(callee)

    async def _write_log_ctx(self, data: List[Tuple[str, int, Any]], primary_id: str):
        async def callee(session):
            for field, key, value in data:
                request = f"""
                    PRAGMA TablePathPrefix("{self.database}");
                    DECLARE ${ExtraFields.primary_id.value} AS Utf8;
                    SELECT {ExtraFields.created_at.value}
                    FROM {self.table_prefix}_{self._LOGS_TABLE}
                    WHERE {ExtraFields.primary_id.value} = ${ExtraFields.primary_id.value};
                """

                existing_context = await session.transaction(SerializableReadWrite()).execute(
                    await session.prepare(request),
                    {f"${ExtraFields.primary_id.value}": primary_id},
                    commit_tx=True,
                )

                if len(existing_context[0].rows) > 0:
                    created_at = existing_context[0].rows[0][ExtraFields.created_at.value]
                else:
                    created_at = datetime.datetime.now()

                query = f"""
                    PRAGMA TablePathPrefix("{self.database}");
                    DECLARE ${self._FIELD_COLUMN} AS Utf8;
                    DECLARE ${self._KEY_COLUMN} AS Uint64;
                    DECLARE ${self._VALUE_COLUMN} AS String;
                    DECLARE ${ExtraFields.primary_id.value} AS Utf8;
                    DECLARE ${ExtraFields.created_at.value} AS Timestamp;
                    UPSERT INTO {self.table_prefix}_{self._LOGS_TABLE} ({self._FIELD_COLUMN}, {self._KEY_COLUMN}, {self._VALUE_COLUMN}, {ExtraFields.primary_id.value}, {ExtraFields.created_at.value}, {ExtraFields.updated_at.value})
                    VALUES (${self._FIELD_COLUMN}, ${self._KEY_COLUMN}, ${self._VALUE_COLUMN}, ${ExtraFields.primary_id.value}, ${ExtraFields.created_at.value}, CurrentUtcDatetime());
                    """

                await session.transaction(SerializableReadWrite()).execute(
                    await session.prepare(query),
                    {
                        f"${self._FIELD_COLUMN}": field,
                        f"${self._KEY_COLUMN}": key,
                        f"${self._VALUE_COLUMN}": pickle.dumps(value),
                        f"${ExtraFields.primary_id.value}": primary_id,
                        f"${ExtraFields.created_at.value}": created_at,
                    },
                    commit_tx=True,
                )

        return await self.pool.retry_operation(callee)


async def _init_drive(timeout: int, endpoint: str, database: str, table_name_prefix: str):
    driver = Driver(endpoint=endpoint, database=database)
    client_settings = driver.table_client._table_client_settings.with_allow_truncated_result(True)
    driver.table_client._table_client_settings = client_settings
    await driver.wait(fail_fast=True, timeout=timeout)

    pool = SessionPool(driver, size=10)

    logs_table_name = f"{table_name_prefix}_{YDBContextStorage._LOGS_TABLE}"
    if not await _does_table_exist(pool, database, logs_table_name):
        await _create_logs_table(pool, database, logs_table_name)

    ctx_table_name = f"{table_name_prefix}_{YDBContextStorage._CONTEXTS_TABLE}"
    if not await _does_table_exist(pool, database, ctx_table_name):
        await _create_contexts_table(pool, database, ctx_table_name)

    return driver, pool


async def _does_table_exist(pool, path, table_name) -> bool:
    async def callee(session):
        await session.describe_table(os.path.join(path, table_name))

    try:
        await pool.retry_operation(callee)
        return True
    except SchemeError:
        return False


async def _create_logs_table(pool, path, table_name):
    async def callee(session):
        await session.create_table(
            "/".join([path, table_name]),
            TableDescription()
            .with_column(Column(ExtraFields.primary_id.value, PrimitiveType.Utf8))
            .with_column(Column(ExtraFields.created_at.value, OptionalType(PrimitiveType.Timestamp)))
            .with_column(Column(ExtraFields.updated_at.value, OptionalType(PrimitiveType.Timestamp)))
            .with_column(Column(YDBContextStorage._FIELD_COLUMN, OptionalType(PrimitiveType.Utf8)))
            .with_column(Column(YDBContextStorage._KEY_COLUMN, PrimitiveType.Uint64))
            .with_column(Column(YDBContextStorage._VALUE_COLUMN, OptionalType(PrimitiveType.String)))
            .with_index(TableIndex("logs_primary_id_index").with_index_columns(ExtraFields.primary_id.value))
            .with_index(TableIndex("logs_field_index").with_index_columns(YDBContextStorage._FIELD_COLUMN))
            .with_primary_keys(ExtraFields.primary_id.value, YDBContextStorage._FIELD_COLUMN, YDBContextStorage._KEY_COLUMN),
        )

    return await pool.retry_operation(callee)


async def _create_contexts_table(pool, path, table_name):
    async def callee(session):
        await session.create_table(
            "/".join([path, table_name]),
            TableDescription()
            .with_column(Column(ExtraFields.primary_id.value, PrimitiveType.Utf8))
            .with_column(Column(ExtraFields.storage_key.value, OptionalType(PrimitiveType.Utf8)))
            .with_column(Column(ExtraFields.active_ctx.value, OptionalType(PrimitiveType.Bool)))
            .with_column(Column(ExtraFields.created_at.value, OptionalType(PrimitiveType.Timestamp)))
            .with_column(Column(ExtraFields.updated_at.value, OptionalType(PrimitiveType.Timestamp)))
            .with_column(Column(YDBContextStorage._PACKED_COLUMN, OptionalType(PrimitiveType.String)))
            .with_index(TableIndex("context_key_index").with_index_columns(ExtraFields.storage_key.value))
            .with_index(TableIndex("context_active_index").with_index_columns(ExtraFields.active_ctx.value))
            .with_primary_key(ExtraFields.primary_id.value)
        )

    return await pool.retry_operation(callee)
