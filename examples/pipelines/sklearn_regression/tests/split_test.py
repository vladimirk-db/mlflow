from examples.pipelines.sklearn_regression.steps.split import split_fn
from pandas import DataFrame


def test_split_fn_returns_datasets_with_correct_spec():
    train = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    validation = DataFrame({"a": [1], "b": [4], "c": [7]})
    test = DataFrame({"a": [2], "b": [6], "c": [9]})
    (train_processed, validation_processed, test_processed) = split_fn(train, validation, test)
    assert isinstance(train_processed, DataFrame)
    assert isinstance(validation_processed, DataFrame)
    assert isinstance(test_processed, DataFrame)
