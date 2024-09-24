import datetime as dt
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_validate
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import FunctionTransformer


class Model:
    """
    The Model class handles the creation, evaluation, saving, and loading of a machine learning
    pipeline. It supports feature processing, regression with target transformation, and
    version-controlled model persistence.

    Key features:
    - Define and evaluate a scikit-learn pipeline.
    - Save and load pipelines with versioning.
    - Perform cross-validation and compute evaluation metrics.

    For more details, refer to the scikit-learn documentation: https://scikit-learn.org/stable/documentation.html
    """

    def __init__(self, feature: FeatureUnion | str):
        self._pipeline = (
            self._load(feature)
            if isinstance(feature, str)
            else self._define_pipeline(feature)
        )

    def __getattr__(self, attr):
        return getattr(self._pipeline, attr)

    @staticmethod
    def _load(path: str = "./data/model.pkl") -> Pipeline:
        with open(path, "rb") as f:
            return pickle.load(f)

    @staticmethod
    def _create_dir_if_not_exists(path: str) -> None:
        if not os.path.exists(path):
            os.makedirs(path)

    @staticmethod
    def _define_pipeline(features: FeatureUnion) -> Pipeline:
        return Pipeline(
            [
                ("feature_processing", features),
                (
                    "regressor",
                    TransformedTargetRegressor(
                        regressor=LinearRegression(),  # was LinearRegressor()
                        transformer=FunctionTransformer(
                            func=np.log1p,
                            inverse_func=np.expm1,
                            check_inverse=False,
                        ),
                    ),
                ),
            ]
        )

    def evaluate(self, X: pd.DataFrame, y: pd.DataFrame) -> dict:
        validation = cross_validate(
            estimator=self.pipeline,
            X=X,
            y=y,
            scoring=(
                "r2",
                "neg_mean_squared_error",
                "neg_mean_absolute_error",
                "explained_variance",
            ),
            cv=3,
            return_train_score=True,
            return_estimator=True,
            verbose=10,
        )
        del validation["estimator"]
        return {k: v.mean() for k, v in validation.items()}

    @staticmethod
    def update_path_with_version(path: str, version: str) -> str:
        _dir, basename = os.path.dirname(path), os.path.basename(path)
        basename_without_ext, ext = os.path.splitext(basename)
        return os.path.join(_dir, f"{basename_without_ext}.{version}{ext}")

    def save(self, path: str = "./data/model.pkl", version: str | None = None) -> None:
        if version is None:
            version = dt.datetime.today().strftime("%Y-%m-%d")

        _path = self.update_path_with_version(path, version)
        self._create_dir_if_not_exists(os.path.dirname(_path))

        with open(_path, "wb") as f:
            pickle.dump(self._pipeline, f)
