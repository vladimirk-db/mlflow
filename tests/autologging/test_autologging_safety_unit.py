# pylint: disable=unused-argument

import abc
import copy
import inspect
import os
import pytest
from unittest import mock

import mlflow
import mlflow.utils.autologging_utils as autologging_utils
from mlflow.entities import RunStatus
from mlflow.tracking.client import MlflowClient
from mlflow.utils.autologging_utils import (
    safe_patch,
    autologging_integration,
    exception_safe_function,
    ExceptionSafeClass,
    ExceptionSafeAbstractClass,
    PatchFunction,
    with_managed_run,
    _validate_args,
    _validate_autologging_run,
    _is_testing,
    try_mlflow_log,
)
from mlflow.utils.mlflow_tags import MLFLOW_AUTOLOGGING

from tests.autologging.fixtures import test_mode_off, test_mode_on  # pylint: disable=unused-import


pytestmark = pytest.mark.large


PATCH_DESTINATION_FN_DEFAULT_RESULT = "original_result"


@pytest.fixture(autouse=True)
def turn_test_mode_off_by_default(test_mode_off):
    """
    Most of the unit test cases in this module assume that autologging APIs are operating in a
    standard execution mode (i.e. where test mode is disabled). Accordingly, we turn off autologging
    test mode for this test module by default. Test cases that verify behaviors specific to test
    mode enable test mode explicitly by specifying the `test_mode_on` fixture.

    For more information about autologging test mode, see the docstring for
    :py:func:`mlflow.utils.autologging_utils._is_testing()`.
    """


@pytest.fixture
def patch_destination():
    class PatchObj:
        def __init__(self):
            self.fn_call_count = 0

        def fn(self, *args, **kwargs):
            self.fn_call_count += 1
            return PATCH_DESTINATION_FN_DEFAULT_RESULT

    return PatchObj()


@pytest.fixture
def test_autologging_integration():
    integration_name = "test_integration"

    @autologging_integration(integration_name)
    def autolog(disable=False):
        pass

    autolog()

    return integration_name


@pytest.fixture(autouse=True)
def clean_up_leaked_runs():
    """
    Certain test cases validate safety API behavior when runs are leaked. Leaked runs that
    are not cleaned up between test cases may result in cascading failures that are hard to
    debug. Accordingly, this fixture attempts to end any active runs it encounters and
    throws an exception (which reported as an additional error in the pytest execution output).
    """
    try:
        yield
        assert not mlflow.active_run(), "test case unexpectedly leaked a run!"
    finally:
        while mlflow.active_run():
            mlflow.end_run()


def test_is_testing_respects_environment_variable():
    try:
        prev_env_var_value = os.environ.pop("MLFLOW_AUTOLOGGING_TESTING", None)
        assert not _is_testing()

        os.environ["MLFLOW_AUTOLOGGING_TESTING"] = "false"
        assert not _is_testing()

        os.environ["MLFLOW_AUTOLOGGING_TESTING"] = "true"
        assert _is_testing()
    finally:
        if prev_env_var_value:
            os.environ["MLFLOW_AUTOLOGGING_TESTING"] = prev_env_var_value
        else:
            del os.environ["MLFLOW_AUTOLOGGING_TESTING"]


def test_safe_patch_forwards_expected_arguments_to_function_based_patch_implementation(
    patch_destination, test_autologging_integration
):

    foo_val = None
    bar_val = None

    def patch_impl(original, foo, bar=10):
        nonlocal foo_val
        nonlocal bar_val
        foo_val = foo
        bar_val = bar

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    patch_destination.fn(foo=7, bar=11)
    assert foo_val == 7
    assert bar_val == 11


def test_safe_patch_forwards_expected_arguments_to_class_based_patch(
    patch_destination, test_autologging_integration
):

    foo_val = None
    bar_val = None

    class TestPatch(PatchFunction):
        def _patch_implementation(self, original, foo, bar=10):  # pylint: disable=arguments-differ
            nonlocal foo_val
            nonlocal bar_val
            foo_val = foo
            bar_val = bar

        def _on_exception(self, exception):
            pass

    safe_patch(test_autologging_integration, patch_destination, "fn", TestPatch)
    with mock.patch(
        "mlflow.utils.autologging_utils.PatchFunction.call", wraps=TestPatch.call
    ) as call_mock:
        patch_destination.fn(foo=7, bar=11)
        assert call_mock.call_count == 1
        assert foo_val == 7
        assert bar_val == 11


def test_safe_patch_provides_expected_original_function(
    patch_destination, test_autologging_integration
):
    def original_fn(foo, bar=10):
        return {
            "foo": foo,
            "bar": bar,
        }

    patch_destination.fn = original_fn

    def patch_impl(original, foo, bar):
        return original(foo + 1, bar + 2)

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    assert patch_destination.fn(1, 2) == {"foo": 2, "bar": 4}


def test_safe_patch_provides_expected_original_function_to_class_based_patch(
    patch_destination, test_autologging_integration
):
    def original_fn(foo, bar=10):
        return {
            "foo": foo,
            "bar": bar,
        }

    patch_destination.fn = original_fn

    class TestPatch(PatchFunction):
        def _patch_implementation(self, original, foo, bar=10):  # pylint: disable=arguments-differ
            return original(foo + 1, bar + 2)

        def _on_exception(self, exception):
            pass

    safe_patch(test_autologging_integration, patch_destination, "fn", TestPatch)
    with mock.patch(
        "mlflow.utils.autologging_utils.PatchFunction.call", wraps=TestPatch.call
    ) as call_mock:
        assert patch_destination.fn(1, 2) == {"foo": 2, "bar": 4}
        assert call_mock.call_count == 1


def test_safe_patch_propagates_exceptions_raised_from_original_function(
    patch_destination, test_autologging_integration
):

    exc_to_throw = Exception("Bad original function")

    def original(*args, **kwargs):
        raise exc_to_throw

    patch_destination.fn = original

    patch_impl_called = False

    def patch_impl(original, *args, **kwargs):
        nonlocal patch_impl_called
        patch_impl_called = True
        return original(*args, **kwargs)

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)

    with pytest.raises(Exception) as exc:
        patch_destination.fn()

    assert exc.value == exc_to_throw
    assert patch_impl_called


def test_safe_patch_logs_exceptions_raised_outside_of_original_function_as_warnings(
    patch_destination, test_autologging_integration
):

    exc_to_throw = Exception("Bad patch implementation")

    def patch_impl(original, *args, **kwargs):
        raise exc_to_throw

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    with mock.patch("mlflow.utils.autologging_utils._logger.warning") as logger_mock:
        assert patch_destination.fn() == PATCH_DESTINATION_FN_DEFAULT_RESULT
        assert logger_mock.call_count == 1
        message, formatting_arg1, formatting_arg2 = logger_mock.call_args[0]
        assert "Encountered unexpected error" in message
        assert formatting_arg1 == test_autologging_integration
        assert formatting_arg2 == exc_to_throw


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_safe_patch_propagates_exceptions_raised_outside_of_original_function_in_test_mode(
    patch_destination, test_autologging_integration
):

    exc_to_throw = Exception("Bad patch implementation")

    def patch_impl(original, *args, **kwargs):
        raise exc_to_throw

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    with pytest.raises(Exception) as exc:
        patch_destination.fn()

    assert exc.value == exc_to_throw


def test_safe_patch_calls_original_function_when_patch_preamble_throws(
    patch_destination, test_autologging_integration
):

    patch_impl_called = False

    def patch_impl(original, *args, **kwargs):
        nonlocal patch_impl_called
        patch_impl_called = True
        raise Exception("Bad patch preamble")

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    assert patch_destination.fn() == PATCH_DESTINATION_FN_DEFAULT_RESULT
    assert patch_destination.fn_call_count == 1
    assert patch_impl_called


def test_safe_patch_returns_original_result_without_second_call_when_patch_postamble_throws(
    patch_destination, test_autologging_integration
):

    patch_impl_called = False

    def patch_impl(original, *args, **kwargs):
        nonlocal patch_impl_called
        patch_impl_called = True
        original(*args, **kwargs)
        raise Exception("Bad patch postamble")

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    assert patch_destination.fn() == PATCH_DESTINATION_FN_DEFAULT_RESULT
    assert patch_destination.fn_call_count == 1
    assert patch_impl_called


def test_safe_patch_respects_disable_flag(patch_destination):

    patch_impl_call_count = 0

    @autologging_integration("test_respects_disable")
    def autolog(disable=False):
        def patch_impl(original, *args, **kwargs):
            nonlocal patch_impl_call_count
            patch_impl_call_count += 1
            return original(*args, **kwargs)

        safe_patch("test_respects_disable", patch_destination, "fn", patch_impl)

    autolog(disable=False)
    patch_destination.fn()
    assert patch_impl_call_count == 1

    autolog(disable=True)
    patch_destination.fn()
    assert patch_impl_call_count == 1


def test_safe_patch_returns_original_result_and_ignores_patch_return_value(
    patch_destination, test_autologging_integration
):

    patch_impl_called = False

    def patch_impl(original, *args, **kwargs):
        nonlocal patch_impl_called
        patch_impl_called = True
        return 10

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    assert patch_destination.fn() == PATCH_DESTINATION_FN_DEFAULT_RESULT
    assert patch_destination.fn_call_count == 1
    assert patch_impl_called


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_safe_patch_validates_arguments_to_original_function_in_test_mode(
    patch_destination, test_autologging_integration
):
    def patch_impl(original, *args, **kwargs):
        return original("1", "2", "3")

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)

    with pytest.raises(Exception, match="does not match expected input"), mock.patch(
        "mlflow.utils.autologging_utils._validate_args", wraps=autologging_utils._validate_args
    ) as validate_mock:
        patch_destination.fn("a", "b", "c")

    assert validate_mock.call_count == 1


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_safe_patch_throws_when_autologging_runs_are_leaked_in_test_mode(
    patch_destination, test_autologging_integration
):
    assert autologging_utils._is_testing()

    def leak_run_patch_impl(original, *args, **kwargs):
        mlflow.start_run(nested=True)

    safe_patch(test_autologging_integration, patch_destination, "fn", leak_run_patch_impl)
    with pytest.raises(AssertionError, match="leaked an active run"):
        patch_destination.fn()

    # End the leaked run
    mlflow.end_run()

    with mlflow.start_run():
        # If a user-generated run existed prior to the autologged training session, we expect
        # that safe patch will not throw a leaked run exception
        patch_destination.fn()
        # End the leaked nested run
        mlflow.end_run()

    assert not mlflow.active_run()


def test_safe_patch_does_not_throw_when_autologging_runs_are_leaked_in_standard_mode(
    patch_destination, test_autologging_integration
):
    assert not autologging_utils._is_testing()

    def leak_run_patch_impl(original, *args, **kwargs):
        mlflow.start_run(nested=True)

    safe_patch(test_autologging_integration, patch_destination, "fn", leak_run_patch_impl)
    patch_destination.fn()
    assert mlflow.active_run()

    # End the leaked run
    mlflow.end_run()

    assert not mlflow.active_run()


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_safe_patch_validates_autologging_runs_when_necessary_in_test_mode(
    patch_destination, test_autologging_integration
):
    assert autologging_utils._is_testing()

    def no_tag_run_patch_impl(original, *args, **kwargs):
        with mlflow.start_run(nested=True):
            return original(*args, **kwargs)

    safe_patch(test_autologging_integration, patch_destination, "fn", no_tag_run_patch_impl)

    with mock.patch(
        "mlflow.utils.autologging_utils._validate_autologging_run", wraps=_validate_autologging_run
    ) as validate_run_mock:

        with pytest.raises(
            AssertionError, match="failed to set autologging tag with expected value"
        ):
            patch_destination.fn()
            assert validate_run_mock.call_count == 1

        validate_run_mock.reset_mock()

        with mlflow.start_run(nested=True):
            # If a user-generated run existed prior to the autologged training session, we expect
            # that safe patch will not attempt to validate it
            patch_destination.fn()
            assert not validate_run_mock.called


def test_safe_patch_does_not_validate_autologging_runs_in_standard_mode(
    patch_destination, test_autologging_integration
):
    assert not autologging_utils._is_testing()

    def no_tag_run_patch_impl(original, *args, **kwargs):
        with mlflow.start_run(nested=True):
            return original(*args, **kwargs)

    safe_patch(test_autologging_integration, patch_destination, "fn", no_tag_run_patch_impl)

    with mock.patch(
        "mlflow.utils.autologging_utils._validate_autologging_run", wraps=_validate_autologging_run
    ) as validate_run_mock:

        patch_destination.fn()

        with mlflow.start_run(nested=True):
            # If a user-generated run existed prior to the autologged training session, we expect
            # that safe patch will not attempt to validate it
            patch_destination.fn()

        assert not validate_run_mock.called


def test_safe_patch_manages_run_if_specified_and_sets_expected_run_tags(
    patch_destination, test_autologging_integration
):
    client = MlflowClient()
    active_run = None

    def patch_impl(original, *args, **kwargs):
        nonlocal active_run
        active_run = mlflow.active_run()
        return original(*args, **kwargs)

    with mock.patch(
        "mlflow.utils.autologging_utils.with_managed_run", wraps=with_managed_run
    ) as managed_run_mock:
        safe_patch(
            test_autologging_integration, patch_destination, "fn", patch_impl, manage_run=True
        )
        patch_destination.fn()
        assert managed_run_mock.call_count == 1
        assert active_run is not None
        assert active_run.info.run_id is not None
        assert (
            client.get_run(active_run.info.run_id).data.tags[MLFLOW_AUTOLOGGING]
            == "test_integration"
        )


def test_safe_patch_does_not_manage_run_if_unspecified(
    patch_destination, test_autologging_integration
):

    active_run = None

    def patch_impl(original, *args, **kwargs):
        nonlocal active_run
        active_run = mlflow.active_run()
        return original(*args, **kwargs)

    with mock.patch(
        "mlflow.utils.autologging_utils.with_managed_run", wraps=with_managed_run
    ) as managed_run_mock:
        safe_patch(
            test_autologging_integration, patch_destination, "fn", patch_impl, manage_run=False
        )
        patch_destination.fn()
        assert managed_run_mock.call_count == 0
        assert active_run is None


def test_safe_patch_preserves_signature_of_patched_function(
    patch_destination, test_autologging_integration
):
    def original(a, b, c=10, *, d=11):
        return 10

    patch_destination.fn = original

    patch_impl_called = False

    def patch_impl(original, *args, **kwargs):
        nonlocal patch_impl_called
        patch_impl_called = True
        return original(*args, **kwargs)

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    patch_destination.fn(1, 2)
    assert patch_impl_called
    assert inspect.signature(patch_destination.fn) == inspect.signature(original)


def test_safe_patch_provides_original_function_with_expected_signature(
    patch_destination, test_autologging_integration
):
    def original(a, b, c=10, *, d=11):
        return 10

    patch_destination.fn = original

    original_signature = False

    def patch_impl(original, *args, **kwargs):
        nonlocal original_signature
        original_signature = inspect.signature(original)
        return original(*args, **kwargs)

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_impl)
    patch_destination.fn(1, 2)
    assert original_signature == inspect.signature(original)


def test_exception_safe_function_exhibits_expected_behavior_in_standard_mode():
    assert not autologging_utils._is_testing()

    @exception_safe_function
    def non_throwing_function():
        return 10

    assert non_throwing_function() == 10

    exc_to_throw = Exception("bad implementation")

    @exception_safe_function
    def throwing_function():
        raise exc_to_throw

    with mock.patch("mlflow.utils.autologging_utils._logger.warning") as logger_mock:
        throwing_function()
        assert logger_mock.call_count == 1
        message, formatting_arg = logger_mock.call_args[0]
        assert "unexpected error during autologging" in message
        assert formatting_arg == exc_to_throw


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_exception_safe_function_exhibits_expected_behavior_in_test_mode():
    assert autologging_utils._is_testing()

    @exception_safe_function
    def non_throwing_function():
        return 10

    assert non_throwing_function() == 10

    exc_to_throw = Exception("function error")

    @exception_safe_function
    def throwing_function():
        raise exc_to_throw

    with pytest.raises(Exception) as exc:
        throwing_function()

    assert exc.value == exc_to_throw


@pytest.mark.parametrize(
    "baseclass, metaclass", [(object, ExceptionSafeClass), (abc.ABC, ExceptionSafeAbstractClass)]
)
def test_exception_safe_class_exhibits_expected_behavior_in_standard_mode(baseclass, metaclass):
    assert not autologging_utils._is_testing()

    class NonThrowingClass(baseclass, metaclass=metaclass):
        def function(self):
            return 10

    assert NonThrowingClass().function() == 10

    exc_to_throw = Exception("function error")

    class ThrowingClass(baseclass, metaclass=metaclass):
        def function(self):
            raise exc_to_throw

    with mock.patch("mlflow.utils.autologging_utils._logger.warning") as logger_mock:
        ThrowingClass().function()

        assert logger_mock.call_count == 1

        message, formatting_arg = logger_mock.call_args[0]
        assert "unexpected error during autologging" in message
        assert formatting_arg == exc_to_throw


@pytest.mark.usefixtures(test_mode_on.__name__)
@pytest.mark.parametrize(
    "baseclass, metaclass", [(object, ExceptionSafeClass), (abc.ABC, ExceptionSafeAbstractClass)]
)
def test_exception_safe_class_exhibits_expected_behavior_in_test_mode(baseclass, metaclass):
    assert autologging_utils._is_testing()

    class NonThrowingClass(baseclass, metaclass=metaclass):
        def function(self):
            return 10

    assert NonThrowingClass().function() == 10

    exc_to_throw = Exception("function error")

    class ThrowingClass(baseclass, metaclass=metaclass):
        def function(self):
            raise exc_to_throw

    with pytest.raises(Exception) as exc:
        ThrowingClass().function()

    assert exc.value == exc_to_throw


def test_patch_function_class_call_invokes_implementation_and_returns_result():
    class TestPatchFunction(PatchFunction):
        def _patch_implementation(self, original, *args, **kwargs):
            return 10

        def _on_exception(self, exception):
            pass

    assert TestPatchFunction.call("foo", lambda: "foo") == 10


def test_patch_function_class_call_handles_exceptions_properly():

    called_on_exception = False

    class TestPatchFunction(PatchFunction):
        def _patch_implementation(self, original, *args, **kwargs):
            raise Exception("implementation exception")

        def _on_exception(self, exception):
            nonlocal called_on_exception
            called_on_exception = True
            raise Exception("on_exception exception")

    # Even if an exception is thrown from `_on_exception`, we expect the original
    # exception from the implementation to be surfaced to the caller
    with pytest.raises(Exception, match="implementation exception"):
        TestPatchFunction.call("foo", lambda: "foo")

    assert called_on_exception


def test_with_managed_runs_yields_functions_and_classes_as_expected():
    def patch_function(original, *args, **kwargs):
        pass

    class TestPatch(PatchFunction):
        def _patch_implementation(self, original, *args, **kwargs):
            pass

        def _on_exception(self, exception):
            pass

    assert callable(with_managed_run("test_integration", patch_function))
    assert inspect.isclass(with_managed_run("test_integration", TestPatch))


def test_with_managed_run_with_non_throwing_function_exhibits_expected_behavior():
    client = MlflowClient()

    @with_managed_run
    def patch_function(original, *args, **kwargs):
        return mlflow.active_run()

    run1 = patch_function(lambda: "foo")
    run1_status = client.get_run(run1.info.run_id).info.status
    assert RunStatus.from_string(run1_status) == RunStatus.FINISHED

    with mlflow.start_run() as active_run:
        run2 = patch_function(lambda: "foo")

    assert run2 == active_run
    run2_status = client.get_run(run2.info.run_id).info.status
    assert RunStatus.from_string(run2_status) == RunStatus.FINISHED


def test_with_managed_run_with_throwing_function_exhibits_expected_behavior():
    client = MlflowClient()
    patch_function_active_run = None

    def patch_function(original, *args, **kwargs):
        nonlocal patch_function_active_run
        patch_function_active_run = mlflow.active_run()
        raise Exception("bad implementation")

    patch_function = with_managed_run("test_integration", patch_function)

    with pytest.raises(Exception):
        patch_function(lambda: "foo")

    assert patch_function_active_run is not None
    status1 = client.get_run(patch_function_active_run.info.run_id).info.status
    assert RunStatus.from_string(status1) == RunStatus.FAILED

    with mlflow.start_run() as active_run, pytest.raises(Exception):
        patch_function(lambda: "foo")
        assert patch_function_active_run == active_run
        # `with_managed_run` should not terminate a preexisting MLflow run,
        # even if the patch function throws
        status2 = client.get_run(active_run.info.run_id).info.status
        assert RunStatus.from_string(status2) == RunStatus.FINISHED


def test_with_managed_run_with_non_throwing_class_exhibits_expected_behavior():
    client = MlflowClient()

    class TestPatch(PatchFunction):
        def _patch_implementation(self, original, *args, **kwargs):
            return mlflow.active_run()

        def _on_exception(self, exception):
            pass

    TestPatch = with_managed_run("test_integration", TestPatch)

    run1 = TestPatch.call(lambda: "foo")
    run1_status = client.get_run(run1.info.run_id).info.status
    assert RunStatus.from_string(run1_status) == RunStatus.FINISHED

    with mlflow.start_run() as active_run:
        run2 = TestPatch.call(lambda: "foo")

    assert run2 == active_run
    run2_status = client.get_run(run2.info.run_id).info.status
    assert RunStatus.from_string(run2_status) == RunStatus.FINISHED


def test_with_managed_run_with_throwing_class_exhibits_expected_behavior():
    client = MlflowClient()
    patch_function_active_run = None

    class TestPatch(PatchFunction):
        def _patch_implementation(self, original, *args, **kwargs):
            nonlocal patch_function_active_run
            patch_function_active_run = mlflow.active_run()
            raise Exception("bad implementation")

        def _on_exception(self, exception):
            pass

    TestPatch = with_managed_run("test_integration", TestPatch)

    with pytest.raises(Exception):
        TestPatch.call(lambda: "foo")

    assert patch_function_active_run is not None
    status1 = client.get_run(patch_function_active_run.info.run_id).info.status
    assert RunStatus.from_string(status1) == RunStatus.FAILED

    with mlflow.start_run() as active_run, pytest.raises(Exception):
        TestPatch.call(lambda: "foo")
        assert patch_function_active_run == active_run
        # `with_managed_run` should not terminate a preexisting MLflow run,
        # even if the patch function throws
        status2 = client.get_run(active_run.info.run_id).info.status
        assert RunStatus.from_string(status2) == RunStatus.FINISHED


def test_with_managed_run_sets_specified_run_tags():
    client = MlflowClient()
    tags_to_set = {
        "foo": "bar",
        "num_layers": "7",
    }

    patch_function_1 = with_managed_run(
        "test_integration", lambda original, *args, **kwargs: mlflow.active_run(), tags=tags_to_set
    )
    run1 = patch_function_1(lambda: "foo")
    assert tags_to_set.items() <= client.get_run(run1.info.run_id).data.tags.items()

    class PatchFunction2(PatchFunction):
        def _patch_implementation(self, original, *args, **kwargs):
            return mlflow.active_run()

        def _on_exception(self, exception):
            pass

    patch_function_2 = with_managed_run("test_integration", PatchFunction2, tags=tags_to_set)
    run2 = patch_function_2.call(lambda: "foo")
    assert tags_to_set.items() <= client.get_run(run2.info.run_id).data.tags.items()


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_validate_args_succeeds_when_arg_sets_are_equivalent_or_identical():
    args = (1, "b", ["c"])
    kwargs = {
        "foo": ["bar"],
        "biz": {"baz": 5},
    }

    _validate_args(args, kwargs, args, kwargs)
    _validate_args(args, None, args, None)
    _validate_args(None, kwargs, None, kwargs)

    args_copy = copy.deepcopy(args)
    kwargs_copy = copy.deepcopy(kwargs)

    _validate_args(args, kwargs, args_copy, kwargs_copy)
    _validate_args(args, None, args_copy, None)
    _validate_args(None, kwargs, None, kwargs_copy)


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_validate_args_throws_when_extra_args_are_not_functions_classes_or_lists():
    user_call_args = (1, "b", ["c"])
    user_call_kwargs = {
        "foo": ["bar"],
        "biz": {"baz": 5},
    }

    invalid_type_autologging_call_args = copy.deepcopy(user_call_args)
    invalid_type_autologging_call_args[2].append(10)
    invalid_type_autologging_call_kwargs = copy.deepcopy(user_call_kwargs)
    invalid_type_autologging_call_kwargs["new"] = {}

    with pytest.raises(Exception, match="Invalid new input"):
        _validate_args(
            user_call_args, user_call_kwargs, invalid_type_autologging_call_args, user_call_kwargs
        )

    with pytest.raises(Exception, match="Invalid new input"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, invalid_type_autologging_call_kwargs
        )


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_validate_args_throws_when_extra_args_are_not_exception_safe():
    user_call_args = (1, "b", ["c"])
    user_call_kwargs = {
        "foo": ["bar"],
        "biz": {"baz": 5},
    }

    class Unsafe:
        pass

    unsafe_autologging_call_args = copy.deepcopy(user_call_args)
    unsafe_autologging_call_args += (lambda: "foo",)
    unsafe_autologging_call_kwargs1 = copy.deepcopy(user_call_kwargs)
    unsafe_autologging_call_kwargs1["foo"].append(Unsafe())

    with pytest.raises(Exception, match="not exception-safe"):
        _validate_args(
            user_call_args, user_call_kwargs, unsafe_autologging_call_args, user_call_kwargs
        )

    with pytest.raises(Exception, match="Invalid new input"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, unsafe_autologging_call_kwargs1
        )

    unsafe_autologging_call_kwargs2 = copy.deepcopy(user_call_kwargs)
    unsafe_autologging_call_kwargs2["biz"]["new"] = Unsafe()

    with pytest.raises(Exception, match="Invalid new input"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, unsafe_autologging_call_kwargs2
        )


@pytest.mark.usefixtures(test_mode_on.__name__)
@pytest.mark.parametrize(
    "baseclass, metaclass", [(object, ExceptionSafeClass), (abc.ABC, ExceptionSafeAbstractClass)]
)
def test_validate_args_succeeds_when_extra_args_are_exception_safe_functions_or_classes(
    baseclass, metaclass
):
    user_call_args = (1, "b", ["c"])
    user_call_kwargs = {
        "foo": ["bar"],
    }

    class Safe(baseclass, metaclass=metaclass):
        pass

    autologging_call_args = copy.deepcopy(user_call_args)
    autologging_call_args[2].append(Safe())
    autologging_call_args += (exception_safe_function(lambda: "foo"),)

    autologging_call_kwargs = copy.deepcopy(user_call_kwargs)
    autologging_call_kwargs["foo"].append(exception_safe_function(lambda: "foo"))
    autologging_call_kwargs["new"] = Safe()

    _validate_args(user_call_args, user_call_kwargs, autologging_call_args, autologging_call_kwargs)


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_validate_args_throws_when_args_are_omitted():
    user_call_args = (1, "b", ["c"], {"d": "e"})
    user_call_kwargs = {
        "foo": ["bar"],
        "biz": {"baz": 4, "fuzz": 5},
    }

    invalid_autologging_call_args_1 = copy.deepcopy(user_call_args)
    invalid_autologging_call_args_1[2].pop()
    invalid_autologging_call_kwargs_1 = copy.deepcopy(user_call_kwargs)
    invalid_autologging_call_kwargs_1["foo"].pop()

    with pytest.raises(Exception, match="missing from the call"):
        _validate_args(
            user_call_args, user_call_kwargs, invalid_autologging_call_args_1, user_call_kwargs
        )

    with pytest.raises(Exception, match="missing from the call"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, invalid_autologging_call_kwargs_1
        )

    invalid_autologging_call_args_2 = copy.deepcopy(user_call_args)[1:]
    invalid_autologging_call_kwargs_2 = copy.deepcopy(user_call_kwargs)
    invalid_autologging_call_kwargs_2.pop("foo")

    with pytest.raises(Exception, match="missing from the call"):
        _validate_args(
            user_call_args, user_call_kwargs, invalid_autologging_call_args_2, user_call_kwargs
        )

    with pytest.raises(Exception, match="omit one or more expected keys"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, invalid_autologging_call_kwargs_2
        )

    invalid_autologging_call_args_3 = copy.deepcopy(user_call_args)
    invalid_autologging_call_args_3[3].pop("d")
    invalid_autologging_call_kwargs_3 = copy.deepcopy(user_call_kwargs)
    invalid_autologging_call_kwargs_3["biz"].pop("baz")

    with pytest.raises(Exception, match="omit one or more expected keys"):
        _validate_args(
            user_call_args, user_call_kwargs, invalid_autologging_call_args_3, user_call_kwargs
        )

    with pytest.raises(Exception, match="omit one or more expected keys"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, invalid_autologging_call_kwargs_3
        )


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_validate_args_throws_when_arg_types_or_values_are_changed():
    user_call_args = (1, "b", ["c"])
    user_call_kwargs = {
        "foo": ["bar"],
    }

    invalid_autologging_call_args_1 = copy.deepcopy(user_call_args)
    invalid_autologging_call_args_1 = (2,) + invalid_autologging_call_args_1[1:]
    invalid_autologging_call_kwargs_1 = copy.deepcopy(user_call_kwargs)
    invalid_autologging_call_kwargs_1["foo"] = ["biz"]

    with pytest.raises(Exception, match="does not match expected input"):
        _validate_args(
            user_call_args, user_call_kwargs, invalid_autologging_call_args_1, user_call_kwargs
        )

    with pytest.raises(Exception, match="does not match expected input"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, invalid_autologging_call_kwargs_1
        )

    call_arg_1, call_arg_2, _ = copy.deepcopy(user_call_args)
    invalid_autologging_call_args_2 = ({"7": 1}, call_arg_1, call_arg_2)
    invalid_autologging_call_kwargs_2 = copy.deepcopy(user_call_kwargs)
    invalid_autologging_call_kwargs_2["foo"] = 8

    with pytest.raises(Exception, match="does not match expected type"):
        _validate_args(
            user_call_args, user_call_kwargs, invalid_autologging_call_args_2, user_call_kwargs
        )

    with pytest.raises(Exception, match="does not match expected type"):
        _validate_args(
            user_call_args, user_call_kwargs, user_call_args, invalid_autologging_call_kwargs_2
        )


def test_validate_autologging_run_validates_autologging_tag_correctly():
    with mlflow.start_run():
        run_id_1 = mlflow.active_run().info.run_id

    with pytest.raises(AssertionError, match="failed to set autologging tag with expected value"):
        _validate_autologging_run("test_integration", run_id_1)

    with mlflow.start_run(tags={MLFLOW_AUTOLOGGING: "wrong_value"}):
        run_id_2 = mlflow.active_run().info.run_id

    with pytest.raises(
        AssertionError, match="failed to set autologging tag with expected value.*wrong_value"
    ):
        _validate_autologging_run("test_integration", run_id_2)

    with mlflow.start_run(tags={MLFLOW_AUTOLOGGING: "test_integration"}):
        run_id_3 = mlflow.active_run().info.run_id

    _validate_autologging_run("test_integration", run_id_3)


def test_validate_autologging_run_validates_run_status_correctly():
    valid_autologging_tags = {
        MLFLOW_AUTOLOGGING: "test_integration",
    }

    with mlflow.start_run(tags=valid_autologging_tags) as run_finished:
        run_id_finished = run_finished.info.run_id

    assert (
        RunStatus.from_string(MlflowClient().get_run(run_id_finished).info.status)
        == RunStatus.FINISHED
    )
    _validate_autologging_run("test_integration", run_id_finished)

    with mlflow.start_run(tags=valid_autologging_tags) as run_failed:
        run_id_failed = run_failed.info.run_id

    MlflowClient().set_terminated(run_id_failed, status=RunStatus.to_string(RunStatus.FAILED))
    assert (
        RunStatus.from_string(MlflowClient().get_run(run_id_failed).info.status) == RunStatus.FAILED
    )
    _validate_autologging_run("test_integration", run_id_finished)

    run_non_terminal = MlflowClient().create_run(
        experiment_id=run_finished.info.experiment_id, tags=valid_autologging_tags
    )
    run_id_non_terminal = run_non_terminal.info.run_id
    assert (
        RunStatus.from_string(MlflowClient().get_run(run_id_non_terminal).info.status)
        == RunStatus.RUNNING
    )
    with pytest.raises(AssertionError, match="has a non-terminal status"):
        _validate_autologging_run("test_integration", run_id_non_terminal)


def test_try_mlflow_log_emits_exceptions_as_warnings_in_standard_mode():
    assert not autologging_utils._is_testing()

    def throwing_function():
        raise Exception("bad implementation")

    with pytest.warns(UserWarning, match="bad implementation"):
        try_mlflow_log(throwing_function)


@pytest.mark.usefixtures(test_mode_on.__name__)
def test_try_mlflow_log_propagates_exceptions_in_test_mode():
    assert autologging_utils._is_testing()

    def throwing_function():
        raise Exception("bad implementation")

    with pytest.raises(Exception, match="bad implementation"):
        try_mlflow_log(throwing_function)


def test_session_manager_creates_session_before_patch_executes(
    patch_destination, test_autologging_integration
):
    is_session_active = None

    def check_session_manager_status(original):
        nonlocal is_session_active
        is_session_active = autologging_utils._AutologgingSessionManager.active_session()

    safe_patch(test_autologging_integration, patch_destination, "fn", check_session_manager_status)
    patch_destination.fn()
    assert is_session_active is not None


def test_session_manager_exits_session_after_patch_executes(
    patch_destination, test_autologging_integration
):
    def patch_fn(original):
        assert autologging_utils._AutologgingSessionManager.active_session() is not None

    safe_patch(test_autologging_integration, patch_destination, "fn", patch_fn)
    patch_destination.fn()
    assert autologging_utils._AutologgingSessionManager.active_session() is None


def test_session_manager_exits_session_if_error_in_patch(
    patch_destination, test_autologging_integration
):
    def patch_fn(original):
        raise Exception("Exception that should stop autologging session")

    # If use safe_patch to patch, exception would not come from original fn and so would be logged
    patch_destination.fn = patch_fn
    with pytest.raises(Exception):
        patch_destination.fn()

    assert autologging_utils._AutologgingSessionManager.active_session() is None


def test_original_fn_runs_if_patch_should_not_be_applied(patch_destination):
    patch_impl_call_count = 0

    @autologging_integration("test_respects_exclusive")
    def autolog(disable=False, exclusive=False):
        def patch_impl(original, *args, **kwargs):
            nonlocal patch_impl_call_count
            patch_impl_call_count += 1
            return original(*args, **kwargs)

        safe_patch("test_respects_exclusive", patch_destination, "fn", patch_impl)

    autolog(exclusive=True)
    with mlflow.start_run():
        patch_destination.fn()
    assert patch_impl_call_count == 0
    assert patch_destination.fn_call_count == 1


def test_patch_runs_if_patch_should_be_applied():
    patch_impl_call_count = 0

    class TestPatchWithNewFnObj:
        def __init__(self):
            self.fn_call_count = 0

        def fn(self, *args, **kwargs):
            self.fn_call_count += 1
            return PATCH_DESTINATION_FN_DEFAULT_RESULT

        def new_fn(self, *args, **kwargs):
            with mlflow.start_run():
                self.fn()

    patch_obj = TestPatchWithNewFnObj()

    @autologging_integration("test_respects_exclusive")
    def autolog(disable=False, exclusive=False):
        def patch_impl(original, *args, **kwargs):
            nonlocal patch_impl_call_count
            patch_impl_call_count += 1

        def new_fn_patch(original, *args, **kwargs):
            pass

        safe_patch("test_respects_exclusive", patch_obj, "fn", patch_impl)
        safe_patch("test_respects_exclusive", patch_obj, "new_fn", new_fn_patch)

    # Should patch if no active run
    autolog()
    patch_obj.fn()
    assert patch_impl_call_count == 1

    # Should patch if active run, but not exclusive
    autolog(exclusive=False)
    with mlflow.start_run():
        patch_obj.fn()
    assert patch_impl_call_count == 2

    # Should patch if active run and exclusive, but active autologging session
    autolog(exclusive=True)
    patch_obj.new_fn()
    assert patch_impl_call_count == 3
