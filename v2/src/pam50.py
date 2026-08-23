"""PAM50 nearest-centroid classifier used by the NB01 gate."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score
from sklearn.neighbors import NearestCentroid

# Parker et al. 2009 PAM50 genes (ORC6L → ORC6).
PAM50_GENES = [
    "ACTR3B", "ANLN", "BAG1", "BCL2", "BIRC5", "BLVRA", "CCNB1", "CCNE1",
    "CDC20", "CDC6", "CDH3", "CENPF", "CEP55", "CXXC5", "EGFR", "ERBB2",
    "ESR1", "EXO1", "FGFR4", "FOXA1", "FOXC1", "GPR160", "GRB7", "KIF2C",
    "KRT14", "KRT17", "KRT5", "MAPT", "MDM2", "MELK", "MIA", "MKI67",
    "MLPH", "MMP11", "MYBL2", "MYC", "NAT1", "NDC80", "NUF2", "ORC6",
    "PGR", "PHGDH", "PTTG1", "RRM2", "SFRP1", "SLC39A6", "TMEM45B",
    "TYMS", "UBE2C", "UBE2T",
]


def normalize_pam50_label(label) -> str:
    s = str(label).strip()
    s = s.replace("BRCA_", "").replace("Her2-enriched", "Her2")
    s = s.replace("Luminal A", "LumA").replace("Luminal B", "LumB")
    if s.lower() in {"nan", "nc", "unknown", "claudin-low"}:
        return s
    return s


def shared_pam50(columns) -> list[str]:
    available = set(columns)
    genes = [g for g in PAM50_GENES if g in available]
    if "ORC6" not in genes and "ORC6L" in available:
        genes.append("ORC6L")
    return genes


def fit_predict_pam50(
    train_X: pd.DataFrame,
    train_y: pd.Series,
    test_X: pd.DataFrame,
) -> np.ndarray:
    genes = shared_pam50(set(train_X.columns) & set(test_X.columns))
    if len(genes) < 20:
        raise ValueError(f"Too few PAM50 genes in intersection: {len(genes)}")
    clf = NearestCentroid()
    clf.fit(train_X[genes].to_numpy(float), train_y.astype(str).to_numpy())
    return clf.predict(test_X[genes].to_numpy(float))


def pam50_scores(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=str)
    y_pred = np.asarray(y_pred, dtype=str)
    concordance = float((y_true == y_pred).mean())
    bal_acc = float(balanced_accuracy_score(y_true, y_pred))
    return {"concordance": concordance, "balanced_accuracy": bal_acc, "n_test": int(len(y_true))}
