import inspect
import functools
import warnings
import logging

import mlflow
from mlflow.entities.run_status import RunStatus
from mlflow.utils import gorilla


INPUT_EXAMPLE_SAMPLE_ROWS = 5
ENSURE_AUTOLOGGING_ENABLED_TEXT = (
    "please ensure that autologging is enabled before constructing the dataset."
)

AUTOLOGGING_INTEGRATIONS = {}

_logger = logging.getLogger(__name__)


def try_mlflow_log(fn, *args, **kwargs):
    """
    Catch exceptions and log a warning to avoid autolog throwing.
    """
    try:
        fn(*args, **kwargs)
    except Exception as e:  # pylint: disable=broad-except
        warnings.warn("Logging to MLflow failed: " + str(e), stacklevel=2)


def get_unspecified_default_args(user_args, user_kwargs, all_param_names, all_default_values):
    """
    Determine which default values are used in a call, given args and kwargs that are passed in.

    :param user_args: list of arguments passed in by the user
    :param user_kwargs: dictionary of kwargs passed in by the user
    :param all_param_names: names of all of the parameters of the function
    :param all_default_values: values of all default parameters
    :return: a dictionary mapping arguments not specified by the user -> default value
    """
    num_args_without_default_value = len(all_param_names) - len(all_default_values)

    # all_default_values correspond to the last len(all_default_values) elements of the arguments
    default_param_names = all_param_names[num_args_without_default_value:]

    default_args = dict(zip(default_param_names, all_default_values))

    # The set of keyword arguments that should not be logged with default values
    user_specified_arg_names = set(user_kwargs.keys())

    num_user_args = len(user_args)

    # This checks if the user passed values for arguments with default values
    if num_user_args > num_args_without_default_value:
        num_default_args_passed_as_positional = num_user_args - num_args_without_default_value
        # Adding the set of positional arguments that should not be logged with default values
        names_to_exclude = default_param_names[:num_default_args_passed_as_positional]
        user_specified_arg_names.update(names_to_exclude)

    return {
        name: value for name, value in default_args.items() if name not in user_specified_arg_names
    }


def log_fn_args_as_params(fn, args, kwargs, unlogged=[]):  # pylint: disable=W0102
    """
    Log parameters explicitly passed to a function.
    :param fn: function whose parameters are to be logged
    :param args: arguments explicitly passed into fn
    :param kwargs: kwargs explicitly passed into fn
    :param unlogged: parameters not to be logged
    :return: None
    """
    # all_default_values has length n, corresponding to values of the
    # last n elements in all_param_names
    pos_params, _, _, pos_defaults, kw_params, kw_defaults, _ = inspect.getfullargspec(fn)

    kw_params = list(kw_params) if kw_params else []
    pos_defaults = list(pos_defaults) if pos_defaults else []
    all_param_names = pos_params + kw_params
    all_default_values = pos_defaults + [kw_defaults[param] for param in kw_params]

    # Checking if default values are present for logging. Known bug that getargspec will return an
    # empty argspec for certain functions, despite the functions having an argspec.
    if all_default_values is not None and len(all_default_values) > 0:
        # Logging the default arguments not passed by the user
        defaults = get_unspecified_default_args(args, kwargs, all_param_names, all_default_values)

        for name in [name for name in defaults.keys() if name in unlogged]:
            del defaults[name]
        try_mlflow_log(mlflow.log_params, defaults)

    # Logging the arguments passed by the user
    args_dict = dict(
        (param_name, param_val)
        for param_name, param_val in zip(all_param_names, args)
        if param_name not in unlogged
    )

    if args_dict:
        try_mlflow_log(mlflow.log_params, args_dict)

    # Logging the kwargs passed by the user
    for param_name in kwargs:
        if param_name not in unlogged:
            try_mlflow_log(mlflow.log_param, param_name, kwargs[param_name])


def wrap_patch(destination, name, patch, settings=None):
    """
    Apply a patch while preserving the attributes (e.g. __doc__) of an original function.

    :param destination: Patch destination
    :param name: Name of the attribute at the destination
    :param patch: Patch function
    :param settings: Settings for gorilla.Patch
    """
    if settings is None:
        settings = gorilla.Settings(allow_hit=True, store_hit=True)

    original = getattr(destination, name)
    wrapped = functools.wraps(original)(patch)
    patch = gorilla.Patch(destination, name, wrapped, settings=settings)
    gorilla.apply(patch)


class _InputExampleInfo:
    """
    Stores info about the input example collection before it is needed.

    For example, in xgboost and lightgbm, an InputExampleInfo object is attached to the dataset,
    where its value is read later by the train method.

    Exactly one of input_example or error_msg should be populated.
    """

    def __init__(self, input_example=None, error_msg=None):
        self.input_example = input_example
        self.error_msg = error_msg


def resolve_input_example_and_signature(
    get_input_example, infer_model_signature, log_input_example, log_model_signature, logger
):
    """
    Handles the logic of calling functions to gather the input example and infer the model
    signature.

    :param get_input_example: function which returns an input example, usually sliced from a
                              dataset. This function can raise an exception, its message will be
                              shown to the user in a warning in the logs.
    :param infer_model_signature: function which takes an input example and returns the signature
                                  of the inputs and outputs of the model. This function can raise
                                  an exception, its message will be shown to the user in a warning
                                  in the logs.
    :param log_input_example: whether to log errors while collecting the input example, and if it
                              succeeds, whether to return the input example to the user. We collect
                              it even if this parameter is False because it is needed for inferring
                              the model signature.
    :param log_model_signature: whether to infer and return the model signature.
    :param logger: the logger instance used to log warnings to the user during input example
                   collection and model signature inference.

    :return: A tuple of input_example and signature. Either or both could be None based on the
             values of log_input_example and log_model_signature.
    """

    input_example = None
    input_example_user_msg = None
    input_example_failure_msg = None
    if log_input_example or log_model_signature:
        try:
            input_example = get_input_example()
        except Exception as e:  # pylint: disable=broad-except
            input_example_failure_msg = str(e)
            input_example_user_msg = "Failed to gather input example: " + str(e)

    model_signature = None
    model_signature_user_msg = None
    if log_model_signature:
        try:
            if input_example is None:
                raise Exception(
                    "could not sample data to infer model signature: " + input_example_failure_msg
                )
            model_signature = infer_model_signature(input_example)
        except Exception as e:  # pylint: disable=broad-except
            model_signature_user_msg = "Failed to infer model signature: " + str(e)

    if log_input_example and input_example_user_msg is not None:
        logger.warning(input_example_user_msg)
    if log_model_signature and model_signature_user_msg is not None:
        logger.warning(model_signature_user_msg)

    return input_example if log_input_example else None, model_signature




def safe_patch(autologging_integration, destination, function_name, function):
    """
    Patches the specified `function_name` on the specified `destination` class for autologging
    purposes, replacing its implementation with an error-safe copy of the specified `function`.

    :param autologging_integration: The name of the autologging integration associated with the
                                    patch.
    :param destination: The Python class on which the patch function is being defined.
    :param function_name: The name of the function to patch on the specified `destination` class.
    :param function: The patch function to apply. This first argument to this function should be
                     reserved for an `original` method argument representing the underlying /
                     original function. Subsequent arguments should be identical to those of the
                     original function being patched.
    """
    def patched_train(*args, **kwargs):
        preexisting_run = mlflow.active_run()
        original_result = None
        failed_during_original = False

        def call_original(*args, **kwargs):
            original = gorilla.get_original_attribute(destination, function_name)

            def wrapped_original(*args, **kwargs):
                try:
                    nonlocal original_result
                    original_result = original(*args, **kwargs)
                    return original_result
                except Exception:
                    nonlocal failed_during_original
                    failed_during_original = True
                    raise

            return wrapped_original(*args, **kwargs)

        original = gorilla.get_original_attribute(destination, function_name)
        config = AUTOLOGGING_INTEGRATIONS[autologging_integration]
        if config.get("disable", False):
            return original(*args, **kwargs)

        try:
            return function(call_original, *args, **kwargs)
        except Exception as e:
            if not preexisting_run and mlflow.active_run():
                try_mlflow_log(mlflow.end_run, RunStatus.to_string(RunStatus.FAILED))

            if failed_during_original:
                raise

            _logger.warning("Encountered unexpected error during %s autologging: %s", autologging_integration, e)

            if original_result:
                return original
            else:
                return original(*args, **kwargs)

    wrap_patch(destination, function_name, patched_train)


def autologging_integration(name):

    AUTOLOGGING_INTEGRATIONS[name] = {}

    def wrapper(_autolog):

        def autolog(*args, **kwargs):
            AUTOLOGGING_INTEGRATIONS[name] = kwargs
            _autolog(**kwargs)

        wrapped_autolog = functools.wraps(_autolog)(autolog)
        return wrapped_autolog

    return wrapper


def handle_exceptions(function):
    """
    Wraps the specified function with broad exception handling to guard
    against unexpected errors during autologging.
    """
    @functools.wraps(function)
    def safe_function(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as e:
            _logger.warning("Encountered unexpected error during autologging: %s", e)
    return safe_function


class ExceptionSafeClass(type):
    """
    Metaclass that wraps all functions defined on the specified class with broad error handling
    logic to guard against unexpected errors during autlogging.

    Rationale: Patched autologging functions commonly pass additional class instances as arguments
    to their underlying original training routines; for example, Keras autologging constructs
    a subclass of `keras.callbacks.Callback` and forwards it to `Model.fit()`. To prevent errors
    encountered during method execution within such classes from disrupting model training,
    this metaclass wraps all class functions in a broad try / catch statement.
    """
    def __new__(cls, name, bases, dct):
        for m in dct:
            if hasattr(dct[m], '__call__'):
                dct[m] = handle_exceptions(dct[m])
        return type.__new__(cls, name, bases, dct)
