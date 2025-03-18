from __future__ import annotations

from typing import TYPE_CHECKING

from big_medicine.utils.logging import Logger

if TYPE_CHECKING:
    import pandas as pd


def upload(
    data: pd.DataFrame,
    keyspace_name: str,
    replication_factor: int,
) -> None:
    from cassandra.cqlengine.management import (
        create_keyspace_simple,
        sync_table,
    )

    from big_medicine.core.server import Medicine

    msg = f"Creating keyspace {keyspace_name} with {replication_factor=}"
    Logger.info(msg)
    create_keyspace_simple(keyspace_name, replication_factor)

    Logger.info(f"Synchronizing table schema {Medicine.__name__}")
    sync_table(Medicine, keyspaces=[keyspace_name])
