import os
import pytest

from mlflow.exceptions import MlflowException
from mlflow.pipelines.regression.v1.pipeline import RegressionPipeline

# pylint: disable=unused-import
from tests.pipelines.helper_functions import (
    enter_pipeline_example_directory,
)  # pylint: enable=unused-import
from unittest import mock


@pytest.fixture
def create_pipeline(enter_pipeline_example_directory):
    pipeline_root_path = enter_pipeline_example_directory
    profile = "local"
    return RegressionPipeline(pipeline_root_path=pipeline_root_path, profile=profile)


def test_create_pipeline_works(enter_pipeline_example_directory):
    pipeline_root_path = enter_pipeline_example_directory
    pipeline_name = os.path.basename(pipeline_root_path)
    profile = "local"
    p = RegressionPipeline(pipeline_root_path=pipeline_root_path, profile=profile)
    assert p.name == pipeline_name
    assert p.profile == profile


@pytest.mark.parametrize(
    "pipeline_name,profile",
    [("name_a", "local"), ("", "local"), ("sklearn_regression", "profile_a")],
)
def test_create_pipeline_fails_with_invalid_input(
    pipeline_name, profile, enter_pipeline_example_directory
):
    pipeline_root_path = os.path.join(
        os.path.dirname(enter_pipeline_example_directory), pipeline_name
    )
    with pytest.raises(MlflowException, match=r"(Failed to find|does not exist)"):
        RegressionPipeline(pipeline_root_path=pipeline_root_path, profile=profile)


def test_pipeline_run_and_clean_the_whole_pipeline_works(create_pipeline):
    p = create_pipeline
    p.run()
    p.clean()


@pytest.mark.parametrize("step", ["ingest", "split", "transform", "train", "evaluate"])
def test_pipeline_run_and_clean_individual_step_works(step, create_pipeline):
    p = create_pipeline
    p.run(step)
    p.clean(step)


def test_pipeline_inspect_pipeline_dag_works(create_pipeline):
    with mock.patch("webbrowser.open_new") as patched_open_new:
        p = create_pipeline
        p.inspect()
        patched_open_new.assert_called_once()
        dag_file = patched_open_new.call_args[0][0].replace("file://", "")
        assert os.path.exists(dag_file)
