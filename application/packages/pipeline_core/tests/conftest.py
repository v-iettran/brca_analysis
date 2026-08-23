from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def toy_expression() -> pd.DataFrame:
    """A tiny synthetic genes x samples matrix with a clear 2-cluster signal,
    used for fast unit tests that must not touch the real 689 MB METABRIC file."""
    rng = np.random.default_rng(0)
    genes = [f"GENE{i}" for i in range(40)]
    samples_a = [f"S_A{i}" for i in range(15)]
    samples_b = [f"S_B{i}" for i in range(15)]

    base = rng.normal(5, 1, size=(40, 30))
    # First 10 genes are up in group A, next 10 up in group B.
    base[:10, :15] += 3
    base[10:20, 15:] += 3
    df = pd.DataFrame(base, index=genes, columns=samples_a + samples_b)
    return df


@pytest.fixture
def toy_labels(toy_expression: pd.DataFrame) -> pd.Series:
    return pd.Series(
        {c: (0 if c.startswith("S_A") else 1) for c in toy_expression.columns}
    )
