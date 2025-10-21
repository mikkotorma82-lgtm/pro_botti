from __future__ import annotations
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import LogisticRegression as _LR
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class SafeLogistic(BaseEstimator, ClassifierMixin):
    """StandardScaler + LogisticRegression turvallisilla oletuksilla."""

    _estimator_type = "classifier"

    def __init__(
        self,
        C: float = 1.0,
        max_iter: int = 1000,
        tol: float = 1e-3,
        penalty: str = "l2",
        class_weight: str | dict | None = "balanced",
        n_jobs: int = -1,
        solver: str = "saga",
        random_state: int | None = 42,
        verbose: int = 0,
        fit_intercept: bool = True,
        warm_start: bool = False,
    ):
        self.C = C
        self.max_iter = max_iter
        self.tol = tol
        self.penalty = penalty
        self.class_weight = class_weight
        self.n_jobs = n_jobs
        self.solver = solver
        self.random_state = random_state
        self.verbose = verbose
        self.fit_intercept = fit_intercept
        self.warm_start = warm_start
        self.pipeline_ = None
        self.classes_ = None

    def _build(self) -> Pipeline:
        clf = _LR(
            C=self.C,
            max_iter=self.max_iter,
            tol=self.tol,
            penalty=self.penalty,
            class_weight=self.class_weight,
            n_jobs=self.n_jobs,
            solver=self.solver,
            random_state=self.random_state,
            verbose=self.verbose,
            fit_intercept=self.fit_intercept,
            warm_start=self.warm_start,
        )
        return Pipeline([("scaler", StandardScaler(with_mean=True)), ("clf", clf)])

    def fit(self, X, y):
        self.pipeline_ = self._build()
        self.pipeline_.fit(X, y)
        self.classes_ = self.pipeline_.named_steps["clf"].classes_
        return self

    def predict_proba(self, X):
        return self.pipeline_.predict_proba(X)

    def predict(self, X):
        return self.pipeline_.predict(X)

    def decision_function(self, X):
        clf = self.pipeline_.named_steps["clf"]
        if hasattr(clf, "decision_function"):
            return self.pipeline_.decision_function(X)
        p = self.predict_proba(X)[:, 1]
        eps = np.finfo(float).eps
        return np.log((p + eps) / (1 - p + eps))

    def score(self, X, y):
        return self.pipeline_.score(X, y)
