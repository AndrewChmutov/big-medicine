from __future__ import annotations

import os
from itertools import count
from typing import TYPE_CHECKING, Any

from big_medicine.utils.logging import Logger

if TYPE_CHECKING:
    import pandas as pd


def upload(
    data: pd.DataFrame,
    keyspace_name: str,
    replication_factor: int,
) -> None:
    os.environ["CQLENG_ALLOW_SCHEMA_MANAGEMENT"] = "1"
    from threading import Event

    import pandas as pd
    from cassandra.cluster import Session
    from cassandra.cqlengine.connection import get_connection
    from cassandra.cqlengine.management import (
        create_keyspace_simple,
        sync_table,
    )
    from cassandra.query import UNSET_VALUE

    from big_medicine.core.server import Medicine, Reservation

    _ = Logger.info
    _(f"Creating keyspace {keyspace_name} with {replication_factor=}")
    create_keyspace_simple(keyspace_name, replication_factor)

    Logger.info("Synchronizing table schemas")
    Medicine.__keyspace__ = keyspace_name  # pyright: ignore[reportAttributeAccessIssue]
    Reservation.__keyspace__ = keyspace_name  # pyright: ignore[reportAttributeAccessIssue]
    sync_table(Medicine)
    sync_table(Reservation)

    guard = object()
    num_queries = data.shape[0]
    num_started = count()
    num_finished = count()
    event = Event()
    data_it = iter(data.iterrows())

    connection = get_connection()
    session: Session = connection.session
    session.set_keyspace(keyspace_name)
    columns = Medicine._columns  # pyright: ignore[reportAttributeAccessIssue]
    prepared_query = session.prepare(
        "INSERT INTO {} ({}) VALUES ({});".format(
            "medicine",
            ", ".join(columns),
            ", ".join("?" for _ in columns),
        )
    )

    def insert_next(previous_result: Any = guard) -> None:
        if previous_result != guard:
            if isinstance(previous_result, BaseException):
                msg = f"An error occurred during insertion: {previous_result}"
                Logger.error(msg)
            if next(num_finished) >= num_queries - 1:
                event.set()
            event.set()

        if next(num_started) < num_queries:
            _, series = next(data_it)
            series = series.fillna(UNSET_VALUE)
            assert isinstance(series, pd.Series)

            query = prepared_query.bind(list(series.values))
            future = session.execute_async(query)
            future.add_callbacks(insert_next, insert_next)

    for _ in range(min(120, num_queries)):
        insert_next()

    event.wait()
