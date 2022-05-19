import pytest
from sklearn.datasets import load_diabetes
from sklearn.linear_model import LinearRegression
from pathlib import Path

import mlflow
from mlflow.utils.file_utils import read_yaml
from mlflow.pipelines.utils import _PIPELINE_CONFIG_FILE_NAME
from mlflow.pipelines.utils.execution import _MLFLOW_PIPELINES_EXECUTION_DIRECTORY_ENV_VAR
from mlflow.pipelines.regression.v1.steps.split import _OUTPUT_TEST_FILE_NAME
from mlflow.pipelines.regression.v1.steps.evaluate import EvaluateStep


@pytest.fixture
def tmp_pipeline_exec_path(monkeypatch, tmp_path) -> Path:
    path = tmp_path.joinpath("pipeline_execution")
    path.mkdir(parents=True)
    monkeypatch.setenv(_MLFLOW_PIPELINES_EXECUTION_DIRECTORY_ENV_VAR, str(path))
    return path


@pytest.fixture
def tmp_pipeline_root_path(tmp_path) -> Path:
    path = tmp_path.joinpath("pipeline_root")
    path.mkdir(parents=True)
    return path


def train_and_log_model():
    mlflow.set_experiment("demo")
    with mlflow.start_run() as run:
        X, y = load_diabetes(as_frame=True, return_X_y=True)
        model = LinearRegression().fit(X, y)
        mlflow.sklearn.log_model(model, artifact_path="model")
    return run.info.run_id


def test_evaluate_step_run(tmp_pipeline_root_path: Path, tmp_pipeline_exec_path: Path):
    split_step_output_dir = tmp_pipeline_exec_path.joinpath("steps", "split", "outputs")
    split_step_output_dir.mkdir(parents=True)
    X, y = load_diabetes(as_frame=True, return_X_y=True)
    test_df = X.assign(y=y).sample(n=100, random_state=42)
    test_df.to_parquet(split_step_output_dir.joinpath(_OUTPUT_TEST_FILE_NAME))

    run_id = train_and_log_model()
    train_step_output_dir = tmp_pipeline_exec_path.joinpath("steps", "train", "outputs")
    train_step_output_dir.mkdir(parents=True)
    train_step_output_dir.joinpath("run_id").write_text(run_id)

    evaluate_step_output_dir = tmp_pipeline_exec_path.joinpath("steps", "evaluate", "outputs")
    evaluate_step_output_dir.mkdir(parents=True)

    pipeline_yaml = tmp_pipeline_root_path.joinpath(_PIPELINE_CONFIG_FILE_NAME)
    pipeline_yaml.write_text(
        """
template: "regression/v1"
target_col: "y"
steps:
  evaluate:
    validation_criteria:
      - metric: root_mean_squared_error
        threshold: 100
      - metric: mean_absolute_error
        threshold: -1
      - metric: weighted_mean_squared_error
        threshold: 100
metrics:
  custom:
    - name: weighted_mean_squared_error
      function: weighted_mean_squared_error
      greater_is_better: False
"""
    )
    pipeline_steps_dir = tmp_pipeline_root_path.joinpath("steps")
    pipeline_steps_dir.mkdir(parents=True)
    pipeline_steps_dir.joinpath("custom_metrics.py").write_text(
        """
from sklearn.metrics import mean_squared_error


def weighted_mean_squared_error(eval_df, builtin_metrics):
    return {
        "weighted_mean_squared_error": mean_squared_error(
            eval_df["prediction"],
            eval_df["target"],
            sample_weight=1 / eval_df["prediction"].values,
        )
    }
"""
    )
    pipeline_config = read_yaml(tmp_pipeline_root_path, _PIPELINE_CONFIG_FILE_NAME)
    evaluate_step = EvaluateStep.from_pipeline_config(pipeline_config, str(tmp_pipeline_root_path))
    evaluate_step._run(str(evaluate_step_output_dir))

    logged_metrics = mlflow.tracking.MlflowClient().get_run(run_id).data.metrics
    logged_metrics = {k.replace("_on_data_test", ""): v for k, v in logged_metrics.items()}
    assert "weighted_mean_squared_error" in logged_metrics
    model_validation_status_path = evaluate_step_output_dir.joinpath("model_validation_status")
    assert model_validation_status_path.exists()
    assert model_validation_status_path.read_text() == "REJECTED"
