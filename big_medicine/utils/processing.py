from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def prepare(
    data: pd.DataFrame,
    low: int,
    high: int,
) -> pd.DataFrame:
    import numpy as np

    data["count"] = np.random.randint(low=low, high=high, size=data.shape[0])
    return data
