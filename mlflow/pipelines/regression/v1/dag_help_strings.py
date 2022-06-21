# pylint: disable=line-too-long


def format_help_string(help_string):
    """
    Formats the specified ``help_string`` to obtain a Mermaid-compatible help string. For example,
    this method replaces quotation marks with their HTML representation.

    :param help_string: The raw help string.
    :return: A Mermaid-compatible help string.
    """
    return help_string.replace('"', "&bsol;#quot;").replace("'", "&bsol;&#39;")


PIPELINE_YAML = format_help_string(
    """# pipeline.yaml is the main configuration file for the pipeline. It defines attributes for each step of the regression pipeline, such as the dataset to use (defined in the 'data' section of the 'ingest' step definition) and the metrics to compute during model training & evaluation (defined in the 'metrics' section, which is used by the 'train' and 'evaluate' steps). pipeline.yaml files also support value overrides from profiles (located in the 'profiles' subdirectory of the pipeline) using Jinja2 templating syntax. An example pipeline.yaml file is displayed below.\n
template: "regression/v1"
# Specifies the dataset to use for model development
data:
  location: {{INGEST_DATA_LOCATION}}
  format: {{INGEST_DATA_FORMAT|default('parquet')}}
  custom_loader_method: steps.ingest.load_file_as_dataframe
target_col: "fare_amount"
steps:
  split:
    split_ratios: {{SPLIT_RATIOS|default([0.75, 0.125, 0.125])}}
    post_split_method: steps.split.process_splits
  transform:
    transform_method: steps.transform.transformer_fn
  train:
    train_method: steps.train.estimator_fn
  evaluate:
    validation_criteria:
      - metric: root_mean_squared_error
        threshold: 10
  register:
    model_name: "taxi_fare_regressor"
    allow_non_validated_model: true
metrics:
  custom:
    - name: weighted_mean_squared_error
      function: weighted_mean_squared_error
      greater_is_better: False
  primary: "root_mean_squared_error"
"""
)

INGEST_STEP = format_help_string(
    """The 'ingest' step resolves the dataset specified by the 'data' section in pipeline.yaml and converts it to parquet format, leveraging the custom dataset parsing code defined in `steps/ingest.py` (and referred to by the 'custom_loader_method' attribute of the 'data' section in pipeline.yaml) if necessary. Subsequent steps convert this dataset into training, validation, & test sets and use them to develop a model. An example pipeline.yaml 'data' configuration is shown below.

data:
  location: https://nyc-tlc.s3.amazonaws.com/trip+data/yellow_tripdata_2022-01.parquet
  format: {{INGEST_DATA_FORMAT|default('parquet')}}
  custom_loader_method: steps.ingest.load_file_as_dataframe
"""
)

INGEST_USER_CODE = format_help_string(
    """\"\"\"\nsteps/ingest.py defines customizable logic for parsing arbitrary dataset formats (i.e. formats that are not natively parsed by MLflow Pipelines) via the `load_file_as_dataframe` function. Note that the Parquet, Delta, and Spark SQL dataset formats are natively parsed by MLflow Pipelines, and you do not need to define custom logic for parsing them. An example `load_file_as_dataframe` implementation is displayed below (note that a different function name or module can be specified via the 'custom_loader_method' attribute of the 'data' section in pipeline.yaml).\n\"\"\"\n
import pandas

def load_file_as_dataframe(
    file_path: str,
    file_format: str,
) -> pandas.DataFrame:
    \"\"\"
    Load content from the specified dataset file as a Pandas DataFrame.

    This method is used to load dataset types that are not natively  managed by MLflow Pipelines (datasets that are not in Parquet, Delta Table, or Spark SQL Table format). This method is called once for each file in the dataset, and MLflow Pipelines automatically combines the resulting DataFrames together.

    :param file_path: The path to the dataset file.
    :param file_format: The file format string, such as "csv".
    :return: A Pandas DataFrame representing the content of the specified file.
    \"\"\"

    if file_format == "csv":
        return pandas.read_csv(file_path, index_col=0)
    else:
        raise NotImplementedError
"""
)

INGESTED_DATA = format_help_string(
    "The ingested parquet representation of the dataset defined in the 'data' section of pipeline.yaml. Subsequent steps convert this dataset into training, validation, & test sets and use them to develop a model."
)

SPLIT_STEP = format_help_string(
    """The 'split' step splits the ingested dataset produced by the 'ingest' step into a training dataset for model training, a validation dataset for model performance evaluation & tuning, and a test dataset for model performance evaluation. The fraction of records allocated to each dataset is defined by the 'split_ratios' attribute of the 'split' step definition in pipeline.yaml. The split step also preprocesses the datasets using logic defined in `steps/split.py` (and referred to by the 'post_split_method' attribute of the 'split' step definition in pipeline.yaml). Subsequent steps use these datasets to develop a model and measure its performance. An example pipeline.yaml 'split' step definition is shown below.

steps:
  split:
    split_ratios: {{SPLIT_RATIOS|default([0.75, 0.125, 0.125])}}
    post_split_method: steps.split.process_splits
"""
)

SPLIT_USER_CODE = format_help_string(
    """\"\"\"\nsteps/split.py defines customizable logic for preprocessing the training, validation, and test datasets prior to model creation via the `process_splits` function, an example of which is displayed below (note that a different function name or module can be specified via the 'post_split_method' attribute of the 'split' step definition in pipeline.yaml).\n\"\"\"\n
import pandas

def process_splits(
    train_df: pandas.DataFrame,
    validation_df: pandas.DataFrame,
    test_df: pandas.DataFrame,
) -> (pandas.DataFrame, pandas.DataFrame, pandas.DataFrame):
    \"\"\"
    Perform additional processing on the split datasets.

    :param train_df: The training dataset.
    :param validation_df: The validation dataset.
    :param test_df: The test dataset.
    :return: A tuple of containing, in order, the processed training dataset, the processed validation dataset, and the processed test dataset.
    \"\"\"

    return train_df.dropna(), validation_df.dropna(), test_df.dropna()
"""
)

TRAINING_AND_VALIDATION_DATA = format_help_string(
    "1. The training dataset used to train the model. Subsequent steps fit a transformer using this training data, create transformed features, and use the transformed features to fit an estimator, producing a model pipeline consisting of the fitted transformer and the fitted estimator.\n\n2. The validation dataset used to evaluate model performance and tune the model pipeline."
)

TEST_DATA = format_help_string(
    "The test dataset used to evaluate the performance of the model. The 'evaluate' step uses the test dataset to compute a variety of performance metrics and model explanations."
)

TRANSFORM_STEP = format_help_string(
    """The 'transform' step uses the training dataset produced by 'split' to fit a transformer with the architecture defined in `steps/transform.py` (and referred to by the 'transform_method' attribute of the 'transform' step definition in pipeline.yaml). The transformer is then applied to the training dataset and the validation dataset, producing transformed datasets that are used by the subsequent 'train' step for estimator training and model performance evaluation. An example pipeline.yaml 'transform' step definition is shown below.

steps:
  transform:
    transform_method: steps.transform.transformer_fn
"""
)

TRANSFORM_USER_CODE = format_help_string(
    """\"\"\"\nsteps/transform.py defines customizable logic for transforming input data during model inference. Transformations are specified via the via the `transformer_fn` function, an example of which is displayed below (note that a different function name or module can be specified via the 'transform_method' attribute of the 'transform' step definition in pipeline.yaml).\n\"\"\"\n
def transformer_fn():
    \"\"\"
    Returns an *unfitted* transformer that defines ``fit()`` and ``transform()`` methods. The transformer's input and output signatures should be compatible with scikit-learn transformers.
    \"\"\"
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    transformers = [
        (
            "hour_encoder",
            OneHotEncoder(categories="auto", sparse=False),
            ["pickup_hour"],
        ),
        (
            "std_scaler",
            StandardScaler(),
            ["trip_distance"],
        ),
    ]
    return Pipeline(steps=[("encoder", ColumnTransformer(transformers)]))
"""
)

FITTED_TRANSFORMER = format_help_string(
    "The fitted transformer produced by fitting the transformer defined in `steps/transform.py` on the training dataset output from the 'split' step. The fitted transformer is the first component of the model pipeline. The subsequent 'train' step fits an estimator and creates a model pipeline consisting of the fitted transformer and the fitted estimator."
)

TRANSFORMED_TRAINING_AND_VALIDATION_DATA = format_help_string(
    "1. The transformed training dataset used to fit the estimator component of the model pipeline. Note that training produces a model pipeline consisting of a fitted transformer and a fitted estimator.\n\n2. The validation dataset used to evaluate estimator performance and tune the estimator."
)

TRAIN_STEP = format_help_string(
    """The 'train' step uses the transformed training dataset produced by 'transform' to fit an estimator with the architecture defined in `steps/train.py` (and referred to by the 'train_method' attribute of the 'train' step definition in pipeline.yaml). The estimator is then joined with the fitted transformer output from the 'transform' step to create a model pipeline. Finally, this model pipeline is evaluated against the transformed training and validation datasets to produce performance metrics; custom metrics are computed according to definitions in `steps/custom_metrics.py` and the 'function' attributes of entries in the 'custom' subsection of the 'metrics' section in pipeline.yaml. The model pipeline and its associated parameters, performance metrics, and lineage information are logged to MLflow Tracking, producing an MLflow Run. An example pipeline.yaml 'train' step definition is shown below, as well as an example custom metric definition.

steps:
  train:
    train_method: steps.train.estimator_fn

metrics:
  custom:
    - name: weighted_mean_squared_error
      function: weighted_mean_squared_error
      greater_is_better: False
"""
)

TRAIN_USER_CODE = format_help_string(
    """\"\"\"\nsteps/train.py defines customizable logic for specifying your estimator's architecture and parameters that will be used during training. Estimator architectures and parameters are specified via the `estimator_fn` function, an example of which is displayed below (note that a different function name or module can be specified via the 'train_method' attribute of the 'train' step definition in pipeline.yaml).\n\"\"\"\n
def estimator_fn():
    \"\"\"
    Returns an *unfitted* estimator that defines ``fit()`` and ``predict()`` methods. The estimator's input and output signatures should be compatible with scikit-learn estimators.
    \"\"\"
    from sklearn.linear_model import SGDRegressor

    return SGDRegressor()
"""
)

FITTED_MODEL = format_help_string(
    "The model pipeline produced by fitting the estimator defined in `steps/train.py` on the training dataset and preceding it with the fitted transformer output by the 'transform' step."
)

MLFLOW_RUN = format_help_string(
    "The MLflow Tracking Run containing the model pipeline & its parameters, model performance metrics on the training & validation datasets, and lineage information about the current pipeline execution. The downstream 'evaluate' step logs performance metrics and model explanations from the test dataset to this MLflow Run."
)

CUSTOM_METRICS_USER_CODE = format_help_string(
    """\"\"\"\nsteps/custom_metrics.py defines customizable logic for specifying custom metrics to compute during model training and evaluation. Custom metric functions defined in `steps/custom_metrics.py` are referenced by the 'function' attributes of entries in the 'custom' subsection of the 'metrics' section in pipeline.yaml. For example:

metrics:
  custom:
    - name: weighted_mean_squared_error
      function: weighted_mean_squared_error
      greater_is_better: False

An example custom_metrics.py file is displayed below.
\"\"\"\


import pandas
from sklearn.metrics import mean_squared_error

def weighted_mean_squared_error(
    eval_df: pandas.DataFrame,
    builtin_metrics: Dict[str, int],
) -> Dict[str, int]:
    \"\"\"
    Computes the weighted mean squared error (MSE) metric.

    :param eval_df: A Pandas DataFrame containing the following columns:

                    - ``"prediction"``: Predictions produced by submitting input data to the model.
                    - ``"target"``: Ground truth values corresponding to the input data.

    :param builtin_metrics: A dictionary containing the built-in metrics that are calculated automatically during model evaluation. The keys are the names of the metrics and the values are the scalar values of the metrics. For more information, see https://mlflow.org/docs/latest/python_api/mlflow.html#mlflow.evaluate.
    :return: A single-entry dictionary containing the MSE metric. The key is the metric names and the value is the scalar metric value. Note that custom metric functions can return dictionaries with multiple metric entries as well.
    \"\"\"
    return {
        "weighted_mean_squared_error": mean_squared_error(
            eval_df["prediction"],
            eval_df["target"],
            sample_weight=1 / eval_df["prediction"].values,
        )
    }
"""
)

EVALUATE_STEP = format_help_string(
    """The 'evaluate' step evaluates the model pipeline produced by the 'train' step on the test dataset output from the 'split step', producing performance metrics and model explanations. Performance metrics are compared against configured thresholds to compute a 'model_validation_status', which indicates whether or not a model is good enough to be registered to the MLflow Model Registry by the subsequent 'register' step. Custom performance metrics are computed according to definitions in `steps/custom_metrics.py` and the 'function' attributes of entries in the 'custom' subsection of the 'metrics' section in pipeline.yaml. Model performance thresholds are defined in the 'validation' section of the 'evaluate' step definition in pipeline.yaml. Model performance metrics and explanations are logged to MLflow Tracking using the same MLflow Run produced by the 'train' step. An example pipeline.yaml 'evaluate' step definition is shown below, as well as an example custom metric definition.

evaluate:
  validation_criteria:
    - metric: root_mean_squared_error
      threshold: 10
    - metric: weighted_mean_squared_error
      threshold: 20

metrics:
  custom:
    - name: weighted_mean_squared_error
      function: weighted_mean_squared_error
      greater_is_better: False
"""
)

MODEL_VALIDATION_STATUS = format_help_string(
    """Boolean status indicating whether or not the model meets the performance criteria for registration to the MLflow Model Registry. Performance criteria are defined in the 'validation_criteria' section of the 'evaluate' step definition in pipeline.yaml, as shown in the example below. The subsequent 'register' step checks the model validation status, and, if it is 'VALIDATED', creates a new model version in the Model Registry corresponding to the trained model pipeline.

evaluate:
  validation_criteria:
    - metric: root_mean_squared_error
      threshold: 10
    - metric: mean_absolute_error
      threshold: 50
    - metric: weighted_mean_squared_error
      threshold: 20
"""
)

REGISTER_STEP = format_help_string(
    """The 'register' step checks the 'model_validation_status' output of the preceding 'evaluate' step and, if model validation was successful (as indicated by the 'VALIDATED' status), registers the model pipeline produced by the 'train' step to the MLflow Model Registry. If the 'model_validation_status' does not indicate that the model passed validation checks (i.e. its value is 'REJECTED'), the model pipeline is not registered to the MLflow Model Registry. This validation status check can be disabled by specifying 'allow_non_validated_model: true' in the 'register' step definition of pipeline.yaml, in which case the model pipeline is always registered with the MLflow Model Registry when the 'register' step is executed. If the model pipeline is registered to the MLflow Model Registry, a 'registered_model_version' is produced containing the model name (as configured by the 'model_name' attribute of the 'register' step definition in pipeline.yaml) and the model version. An example pipeline.yaml 'register' step definition is shown below.

register:
  model_name: "taxi_fare_regressor"
  allow_non_validated_model: true
"""
)

REGISTERED_MODEL_VERSION = format_help_string(
    "The Model Version in the MLflow Model Registry corresponding to the trained model. A Model Version is produced if the trained model meets the defined performance criteria for model registration or if `allow_non_validated_model: true` is specified in the 'register' step definition of pipeline.yaml"
)
