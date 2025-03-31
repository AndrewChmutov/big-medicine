from __future__ import annotations

import os
from itertools import islice
from typing import TYPE_CHECKING

from big_medicine.utils.logging import Logger

if TYPE_CHECKING:
    import pandas as pd


def upload(
    data: pd.DataFrame,
    keyspace_name: str,
    replication_factor: int,
) -> None:
    os.environ["CQLENG_ALLOW_SCHEMA_MANAGEMENT"] = "1"
    import numpy as np
    import pandas as pd
    from cassandra.cqlengine.management import (
        create_keyspace_simple,
        sync_table,
    )
    from cassandra.cqlengine.query import BatchQuery

    from big_medicine.core.server import Medicine, Reservation

    _ = Logger.info
    _(f"Creating keyspace {keyspace_name} with {replication_factor=}")
    create_keyspace_simple(keyspace_name, replication_factor)

    Logger.info(f"Synchronizing table schema {Medicine.__name__}")
    Medicine.__keyspace__ = keyspace_name  # pyright: ignore[reportAttributeAccessIssue]
    Reservation.__keyspace__ = keyspace_name  # pyright: ignore[reportAttributeAccessIssue]
    sync_table(Medicine)
    sync_table(Reservation)

    batch_size = 4
    n_batches = data.shape[0] / batch_size
    n_batches = np.ceil(n_batches, dtype=int, casting="unsafe")
    Logger.info(f"Uploading data in {n_batches} batches")

    i = 0
    it = data.iterrows()
    log_every = 10
    while batch := tuple(islice(it, batch_size)):
        if (i := i + 1) % log_every == 0:
            Logger.info(f"Uploading {i}/{n_batches} batch")
        with BatchQuery() as bq:
            for _, series in batch:
                series = series[~series.isna()]
                assert isinstance(series, pd.Series)
                Medicine.batch(bq).create(**series.to_dict())
