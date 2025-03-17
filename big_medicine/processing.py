from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def prepare(
    data: pd.DataFrame,
    low: int,
    high: int | None = None,
) -> pd.DataFrame:
    import numpy as np

    data["count"] = np.random.randint(low, high, size=data.shape[0])
    return data
