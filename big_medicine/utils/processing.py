from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def prepare(
    data: pd.DataFrame,
    low: int,
    high: int,
    take: int,
) -> pd.DataFrame:
    import numpy as np

    # Shorten
    data = data.iloc[:take]

    # Rename columns
    source_label = "sideEffect"
    target_label = "side_effect"

    def is_side_effect(x: str) -> bool:
        return x.startswith(source_label)

    def process(x: str) -> tuple[str, str]:
        return x, target_label + x.lstrip(source_label)

    columns = filter(is_side_effect, data.columns)
    mapping = {key: value for key, value in map(process, columns)}

    columns = filter(lambda x: not is_side_effect(x), data.columns)
    mapping |= {key: key.lower().replace(" ", "_") for key in columns}

    data = data.rename(mapping, axis="columns")

    # Add column
    data["count"] = np.random.randint(low=low, high=high, size=data.shape[0])

    return data
