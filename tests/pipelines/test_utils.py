import os
import pathlib

import pytest

from mlflow.exceptions import MlflowException
from mlflow.pipelines.utils import get_pipeline_root_path, get_pipeline_name
from mlflow.utils.file_utils import chdir

from tests.pipelines.helper_functions import enter_pipeline_example_directory


def test_get_pipeline_root_path_returns_correctly_when_inside_pipeline_directory(enter_pipeline_example_directory):
    pipeline_root_path = enter_pipeline_example_directory
    get_pipeline_root_path() == pipeline_root_path
    os.chdir(pathlib.Path.cwd() / "notebooks")
    get_pipeline_root_path() == enter_pipeline_example_directory


def test_get_pipeline_root_path_throws_outside_pipeline_directory(tmp_path):
    with pytest.raises(MlflowException, match="Failed to find pipeline.yaml"), chdir(tmp_path):
        get_pipeline_root_path()


def test_get_pipeline_name_returns_correctly_for_valid_pipeline_directory(enter_pipeline_example_directory, tmp_path):
    pipeline_root_path = enter_pipeline_example_directory
    assert pathlib.Path.cwd() == pipeline_root_path
    assert get_pipeline_name() == "sklearn_regression"

    with chdir(tmp_path):
        assert get_pipeline_name(pipeline_root_path=pipeline_root_path) == "sklearn_regression"


def test_get_pipeline_name_throws_for_invalid_pipeline_directory(tmp_path):
    with pytest.raises(MlflowException, match="Failed to find pipeline.yaml"), chdir(tmp_path):
        get_pipeline_name()

    with pytest.raises(MlflowException, match="Yaml file.*does not exist"):
        get_pipeline_name(pipeline_root_path=tmp_path)
