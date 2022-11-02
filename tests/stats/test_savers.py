import pytest
from sqlalchemy import text

from dff.stats import make_saver
from dff.stats.savers.clickhouse import ClickHouseSaver
from dff.stats.savers.postgresql import PostgresSaver

from tests.db_list import POSTGRES_ACTIVE, CLICKHOUSE_ACTIVE


@pytest.mark.skipif(not POSTGRES_ACTIVE, reason="Postgres server is not running")
@pytest.mark.asyncio
async def test_PG_saving(PG_uri_string, table, testing_items):
    saver: PostgresSaver = make_saver(PG_uri_string, table=table)
    await saver._create_table()

    async with saver.engine.connect() as conn:
        await conn.execute(text(f"TRUNCATE {table}"))
        await conn.commit()

    await saver.save(testing_items)
    await saver.save(testing_items)

    async with saver.engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        first = result.first()
    assert int(first[0]) == (len(testing_items) * 2)


@pytest.mark.skipif(not CLICKHOUSE_ACTIVE, reason="Clickhouse server is not running")
@pytest.mark.asyncio
async def test_CH_saving(CH_uri_string, table, testing_items):
    saver: ClickHouseSaver = make_saver(CH_uri_string, table=table)
    await saver._create_table()

    await saver.ch_client.execute(f"TRUNCATE {table}")

    await saver.save(testing_items)
    await saver.save(testing_items)

    result = await saver.ch_client.fetchval(f"SELECT COUNT (*) FROM {table}")
    assert int(result) == (len(testing_items) * 2)
