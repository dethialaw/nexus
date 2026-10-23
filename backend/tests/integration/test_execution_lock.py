from nexus.adapters.persistence.execution_lock import PostgresExecutionLock


async def test_a_second_connection_finds_the_lock_taken_until_it_is_released(
    database_url: str,
) -> None:
    first = PostgresExecutionLock(database_url)
    second = PostgresExecutionLock(database_url)

    assert await first.acquire()
    assert not await second.acquire()
    await first.release()
    assert await second.acquire()
    await second.release()


async def test_the_lock_is_released_when_the_connection_drops(database_url: str) -> None:
    holder = PostgresExecutionLock(database_url)
    assert await holder.acquire()
    assert holder._connection is not None
    raw = await holder._connection.get_raw_connection()
    # Closing the underlying socket is what a crashed batch looks like to the server.
    raw.driver_connection.terminate()  # type: ignore[union-attr]

    other = PostgresExecutionLock(database_url)
    try:
        assert await other.acquire()
    finally:
        await other.release()
        await holder.release()
