import numpy as np
import pandas as pd


def prepare(
    data: pd.DataFrame,
    low: int,
    high: int | None = None,
) -> pd.DataFrame:
    data["count"] = np.random.randint(low, high, size=data.shape[0])
    return data
