import json
import numpy as np

import mlflow.data
from mlflow.data.pyfunc_dataset_mixin import PyFuncInputsOutputs
from mlflow.data.tensorflow_dataset import TensorflowDataset
from mlflow.types.schema import Schema
from mlflow.types.utils import _infer_schema

import tensorflow as tf

from tests.resources.data.dataset_source import TestDatasetSource


def test_conversion_to_json():
    source_uri = "test:/my/test/uri"
    x = np.random.sample((100, 2))
    tf_dataset = tf.data.Dataset.from_tensors(x)
    source = TestDatasetSource._resolve(source_uri)
    dataset = TensorflowDataset(data=tf_dataset, source=source, name="testname")

    dataset_json = dataset.to_json()
    parsed_json = json.loads(dataset_json)
    assert parsed_json.keys() <= {"name", "digest", "source", "source_type", "schema", "profile"}
    assert parsed_json["name"] == dataset.name
    assert parsed_json["digest"] == dataset.digest
    assert parsed_json["source"] == dataset.source.to_json()
    assert parsed_json["source_type"] == dataset.source._get_source_type()
    assert parsed_json["profile"] == json.dumps(dataset.profile)

    schema_json = json.dumps(json.loads(parsed_json["schema"])["mlflow_tensorspec"])
    assert Schema.from_json(schema_json) == dataset.schema


def test_digest_property_has_expected_value():
    source_uri = "test:/my/test/uri"
    x = [[1, 2, 3], [4, 5, 6]]
    tf_dataset = tf.data.Dataset.from_tensors(x)
    source = TestDatasetSource._resolve(source_uri)
    dataset = TensorflowDataset(data=tf_dataset, source=source, name="testname")
    assert dataset.digest == dataset._compute_digest()
    assert dataset.digest == "8c404915"


def test_data_property_has_expected_value():
    source_uri = "test:/my/test/uri"
    x = [[1, 2, 3], [4, 5, 6]]
    tf_dataset = tf.data.Dataset.from_tensors(x)
    source = TestDatasetSource._resolve(source_uri)
    dataset = TensorflowDataset(data=tf_dataset, source=source, name="testname")
    assert dataset.data == tf_dataset


def test_source_property_has_expected_value():
    source_uri = "test:/my/test/uri"
    x = [[1, 2, 3], [4, 5, 6]]
    tf_dataset = tf.data.Dataset.from_tensors(x)
    source = TestDatasetSource._resolve(source_uri)
    dataset = TensorflowDataset(data=tf_dataset, source=source, name="testname")
    assert dataset.source == source


def test_profile_property_has_expected_value_dataset():
    source_uri = "test:/my/test/uri"
    x = [[1, 2, 3], [4, 5, 6]]
    tf_dataset = tf.data.Dataset.from_tensors(x)
    source = TestDatasetSource._resolve(source_uri)
    dataset = TensorflowDataset(data=tf_dataset, source=source, name="testname")
    assert dataset.profile == {
        "num_rows": len(tf_dataset),
        "num_elements": tf_dataset.cardinality().numpy(),
    }


def test_profile_property_has_expected_value_tensors():
    source_uri = "test:/my/test/uri"
    x = [[1, 2, 3], [4, 5, 6]]
    tf_tensor = tf.convert_to_tensor(x)
    source = TestDatasetSource._resolve(source_uri)
    dataset = TensorflowDataset(data=tf_tensor, source=source, name="testname")
    assert dataset.profile == {
        "num_rows": len(tf_tensor),
        "num_elements": tf.size(tf_tensor).numpy(),
    }


def test_to_pyfunc():
    source_uri = "test:/my/test/uri"
    x = np.random.sample((100, 2))
    tf_dataset = tf.data.Dataset.from_tensors(x)
    source = TestDatasetSource._resolve(source_uri)
    dataset = TensorflowDataset(data=tf_dataset, source=source, name="testname")
    assert isinstance(dataset.to_pyfunc(), PyFuncInputsOutputs)


def test_from_tensorflow_dataset_constructs_expected_dataset():
    x = np.random.sample((100, 2))
    tf_dataset = tf.data.Dataset.from_tensors(x)
    mlflow_ds = mlflow.data.from_tensorflow(tf_dataset, source="my_source")
    assert isinstance(mlflow_ds, TensorflowDataset)
    assert mlflow_ds.data == tf_dataset
    assert mlflow_ds.schema == _infer_schema(next(tf_dataset.as_numpy_iterator()))
    assert mlflow_ds.profile == {
        "num_rows": len(tf_dataset),
        "num_elements": tf_dataset.cardinality().numpy(),
    }


def test_from_tensorflow_tensor_constructs_expected_dataset():
    x = np.random.sample((100, 2))
    tf_tensor = tf.convert_to_tensor(x)
    mlflow_ds = mlflow.data.from_tensorflow(tf_tensor, source="my_source")
    assert isinstance(mlflow_ds, TensorflowDataset)
    # compare if two tensors are equal using tensorflow utils
    assert tf.reduce_all(tf.math.equal(mlflow_ds.data, tf_tensor))
    assert mlflow_ds.schema == _infer_schema(tf_tensor.numpy())
    assert mlflow_ds.profile == {
        "num_rows": len(tf_tensor),
        "num_elements": tf.size(tf_tensor).numpy(),
    }