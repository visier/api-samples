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

    def __init__(self):
        self.pipeline: Pipeline | None = None
        self.today: str = dt.datetime.today().strftime("%Y-%m-%d")

    def __is_pipeline_defined(self) -> None:
        if self.pipeline is None:
            raise RuntimeError(
                "pipeline is not defined, please either define or load a pipeline"
            )

    @staticmethod
    def update_path_with_version(path: str, version: str) -> str:
        _dir, basename = os.path.dirname(path), os.path.basename(path)
        basename_without_ext, ext = os.path.splitext(basename)
        return os.path.join(_dir, f"{basename_without_ext}.{version}{ext}")

    @staticmethod
    def create_dir_if_not_exists(path: str) -> None:
        if not os.path.exists(path):
            os.makedirs(path)

    def define_pipeline(self, features: FeatureUnion) -> Pipeline:
        self.pipeline = Pipeline(
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
        return self.pipeline

    def evaluate(self, X: pd.DataFrame, y: pd.DataFrame) -> dict:
        self.__is_pipeline_defined()
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

    def save(self, path: str = "./data/model.pkl", version: str | None = None) -> None:
        self.__is_pipeline_defined()

        if version is None:
            version = self.today

        _path = self.update_path_with_version(path, version)
        self.create_dir_if_not_exists(os.path.dirname(_path))

        pickle.dump(self.pipeline, open(_path, "wb"))

    def load(self, path: str = "./data/model.pkl") -> None:
        self.pipeline = pickle.load(open(path, "rb"))
