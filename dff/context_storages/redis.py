"""
Redis
-----
The Redis module provides a Redis-based version of the :py:class:`.DBContextStorage` class.
This class is used to store and retrieve context data in a Redis.
It allows the `DFF` to easily store and retrieve context data in a format that is highly scalable
and easy to work with.

Redis is an open-source, in-memory data structure store that is known for its
high performance and scalability. It stores data in key-value pairs and supports a variety of data
structures such as strings, hashes, lists, sets, and more.
Additionally, Redis can be used as a cache, message broker, and database, making it a versatile
and powerful choice for data storage and management.
"""
import pickle
from typing import Hashable, List, Dict, Any

try:
    from aioredis import Redis

    redis_available = True
except ImportError:
    redis_available = False

from dff.script import Context

from .database import DBContextStorage, threadsafe_method
from .protocol import get_protocol_install_suggestion
from .update_scheme import default_update_scheme


class RedisContextStorage(DBContextStorage):
    """
    Implements :py:class:`.DBContextStorage` with `redis` as the database backend.

    :param path: Database URI string. Example: `redis://user:password@host:port`.
    :type path: str
    """

    _TOTAL_CONTEXT_COUNT_KEY = "total_contexts"

    def __init__(self, path: str):
        DBContextStorage.__init__(self, path)
        if not redis_available:
            install_suggestion = get_protocol_install_suggestion("redis")
            raise ImportError("`redis` package is missing.\n" + install_suggestion)
        self._redis = Redis.from_url(self.full_path)

    @threadsafe_method
    async def contains_async(self, key: Hashable) -> bool:
        return bool(await self._redis.exists(str(key)))

    async def _write_seq(self, field_name: str, data: Dict[Hashable, Any], int_id: int, ext_id: int):
        for key, value in data.items():
            await self._redis.set(f"{ext_id}:{int_id}:{field_name}:{key}", pickle.dumps(value))

    async def _write_value(self, data: Any, field_name: str, int_id: int, ext_id: int):
        return await self._redis.set(f"{ext_id}:{int_id}:{field_name}", pickle.dumps(data))

    @threadsafe_method
    async def set_item_async(self, key: Hashable, value: Context):
        key = str(key)
        await default_update_scheme.process_fields_write(value, self.hash_storage.get(key, dict()), self._read_fields, self._write_value, self._write_seq, value.id, key)
        last_id = await self._redis.rpop(key)
        if last_id is None or last_id != str(value.id):
            if last_id is not None:
                await self._redis.rpush(key, last_id)
            else:
                await self._redis.incr(RedisContextStorage._TOTAL_CONTEXT_COUNT_KEY)
            await self._redis.rpush(key, str(value.id))

    async def _read_fields(self, field_name: str, int_id: int, ext_id: int):
        return [key.split(":")[-1] for key in await self._redis.keys(f"{ext_id}:{int_id}:{field_name}:*")]

    async def _read_seq(self, field_name: str, outlook: List[int], int_id: int, ext_id: int) -> Dict[Hashable, Any]:
        result = dict()
        for key in outlook:
            value = await self._redis.get(f"{ext_id}:{int_id}:{field_name}:{key}")
            result[key] = pickle.loads(value) if value is not None else None
        return result

    async def _read_value(self, field_name: str, int_id: int, ext_id: int) -> Any:
        value = await self._redis.get(f"{ext_id}:{int_id}:{field_name}")
        return pickle.loads(value) if value is not None else None

    @threadsafe_method
    async def get_item_async(self, key: Hashable) -> Context:
        key = str(key)
        last_id = await self._redis.rpop(key)
        if last_id is None:
            raise KeyError(f"No entry for key {key}.")
        context, hashes = await default_update_scheme.process_fields_read(self._read_fields, self._read_value, self._read_seq, last_id, key)
        self.hash_storage[key] = hashes
        return context

    @threadsafe_method
    async def del_item_async(self, key: Hashable):
        for key in await self._redis.keys(f"{str(key)}:*"):
            await self._redis.delete(key)
        await self._redis.decr(RedisContextStorage._TOTAL_CONTEXT_COUNT_KEY)

    @threadsafe_method
    async def len_async(self) -> int:
        return int(await self._redis.get(RedisContextStorage._TOTAL_CONTEXT_COUNT_KEY))

    @threadsafe_method
    async def clear_async(self):
        await self._redis.flushdb()
        await self._redis.set(RedisContextStorage._TOTAL_CONTEXT_COUNT_KEY, 0)
