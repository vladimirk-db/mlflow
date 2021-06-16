import os
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from typing import Any, Dict, Optional, Union

from mlflow.entities import Param, RunTag, Metric
from mlflow.exceptions import MlflowException
from mlflow.tracking.client import MlflowClient
from mlflow.utils import chunk_list, _truncate_dict
from mlflow.utils.validation import (
    MAX_ENTITIES_PER_BATCH,
    MAX_ENTITY_KEY_LENGTH,
    MAX_TAG_VAL_LENGTH,
    MAX_PARAM_VAL_LENGTH,
    MAX_PARAMS_TAGS_PER_BATCH,
    MAX_METRICS_PER_BATCH,
)


_PendingCreateRun = namedtuple("_PendingCreateRun", ["experiment_id", "start_time", "tags"])
_PendingSetTerminated = namedtuple("_PendingSetTerminated", ["status", "end_time"])


class PendingRunId:
    """
    Serves as a placeholder for the ID of a run that does not yet exist, enabling additional
    metadata (e.g. metrics, params, ...) to be enqueued for the run prior to its creation.
    """


class RunOperations:
    """
    Represents a collection of operations on one or more MLflow Runs, such as run creation
    or metric logging. 
    """

    def __init__(self, operation_futures):
        self._operation_futures = operation_futures

    def await_completion(self):
        """
        Blocks on completion of the MLflow Run operations.
        """
        failed_operations = []
        for future in self._operation_futures:
            try:
                future.result()
            except Exception as e:
                failed_operations.append(e)

        if len(failed_operations) > 0:
            raise MlflowException(
                message=(
                    "The following failures occurred while performing one or more logging"
                    " operations: {failures}".format(failures=failed_operations)
                )
            )


class MlflowAutologgingQueueingClient:
    """
    Efficienty implements a subset of MLflow Tracking's  `MlflowClient` and fluent APIs to provide
    automatic batching and async execution of run operations by way of queueing, as well as
    parameter / tag truncation for autologging use cases. Run operations defined by this client,
    such as `create_run` and `log_metrics`, enqueue data for future persistence to MLflow
    Tracking. Data is not persisted until the queue is flushed via the `flush()` method, which
    supports synchronous and asynchronous execution.

    MlflowAutologgingQueueingClient is not threadsafe; none of its APIs should be called
    concurrently.
    """

    def __init__(self):
        self._client = MlflowClient()
        self._pending_ops_by_run_id = {}

        # Limit the number of threads used for run operations, using at most 8 threads or
        # 2 * the number of CPU cores available on the system (whichever is smaller)
        num_cpus = os.cpu_count() or 4
        num_logging_workers = min(num_cpus * 2, 8)
        self._thread_pool = ThreadPoolExecutor(max_workers=num_logging_workers)

    def create_run(
        self,
        experiment_id: str,
        start_time: Optional[int] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> PendingRunId:
        """
        Enqueues a CreateRun operation with the specified attributes, returning a `PendingRunId`
        instance that can be used as input to other client logging APIs (e.g. `log_metrics`, 
        `log_params`, ...).

        :return: A `PendingRunId` that can be passed as the `run_id` parameter to other client
                 logging APIs, such as `log_params` and `log_metrics`. 
        """
        tags = tags or {}
        tags = _truncate_dict(
            tags, max_key_length=MAX_ENTITY_KEY_LENGTH, max_value_length=MAX_TAG_VAL_LENGTH
        )
        run_id = PendingRunId()
        self._get_pending_operations(run_id).enqueue(
            create_run=_PendingCreateRun(
                experiment_id=experiment_id,
                start_time=start_time,
                tags=[RunTag(key, str(value)) for key, value in tags.items()],
            )
        )
        return run_id

    def set_terminated(
        self,
        run_id: Union[str, PendingRunId],
        status: Optional[str] = None,
        end_time: Optional[int] = None,
    ) -> None:
        """
        Enqueues an UpdateRun operation with the specified `status` and `end_time` attributes
        for the specified `run_id`.
        """
        self._get_pending_operations(run_id).enqueue(
            set_terminated=_PendingSetTerminated(status=status, end_time=end_time,)
        )

    def log_params(self, run_id: Union[str, PendingRunId], params: Dict[str, Any]) -> None:
        """
        Enqueues a collection of Parameters to be logged to the run specified by `run_id`.
        """
        params = _truncate_dict(
            params, max_key_length=MAX_ENTITY_KEY_LENGTH, max_value_length=MAX_PARAM_VAL_LENGTH
        )
        params_arr = [Param(key, str(value)) for key, value in params.items()]
        self._get_pending_operations(run_id).enqueue(params=params_arr)

    def log_metrics(
        self,
        run_id: Union[str, PendingRunId],
        metrics: Dict[str, float],
        step: Optional[int] = None,
    ) -> None:
        """
        Enqueues a collection of Metrics to be logged to the run specified by `run_id` at the
        step specified by `step`.
        """
        metrics = _truncate_dict(metrics, max_key_length=MAX_ENTITY_KEY_LENGTH)
        timestamp = int(time.time() * 1000)
        metrics_arr = [Metric(key, value, timestamp, step or 0) for key, value in metrics.items()]
        self._get_pending_operations(run_id).enqueue(metrics=metrics_arr)

    def set_tags(self, run_id: Union[str, PendingRunId], tags: Dict[str, Any]) -> None:
        """
        Enqueues a collection of Tags to be logged to the run specified by `run_id`.
        """
        tags = _truncate_dict(
            tags, max_key_length=MAX_ENTITY_KEY_LENGTH, max_value_length=MAX_TAG_VAL_LENGTH
        )
        tags_arr = [RunTag(key, str(value)) for key, value in tags.items()]
        self._get_pending_operations(run_id).enqueue(tags=tags_arr)

    def flush(self, synchronous=True):
        """
        Flushes all queued run operations, resulting in the creation or mutation of runs
        and run data.

        :param synchronous: If `True`, run operations are performed synchronously, and a
                            `RunOperations` result object is only returned once all operations
                            are complete. If `False`, run operations are performed asynchronously,
                            and an `RunOperations` object is returned that represents the ongoing
                            run operations.
        :return: A `RunOperations` instance representing the flushed operations. These operations
                 are already complete if `synchronous` is `True`. If `synchronous` is `False`, these
                 operations may still be inflight. Operation completion can be synchronously waited
                 on via `RunOperations.await_completion()`.
        """
        logging_futures = []
        for pending_operations in self._pending_ops_by_run_id.values():
            future = self._thread_pool.submit(
                self._flush_pending_operations, pending_operations=pending_operations,
            )
            logging_futures.append(future)
        self._pending_ops_by_run_id = {}

        logging_operations = RunOperations(logging_futures)
        if synchronous:
            logging_operations.await_completion()
        return logging_operations

    def _get_pending_operations(self, run_id):
        """
        :return: A `_PendingRunOperations` containing all pending operations for the specified
        """
        if run_id not in self._pending_ops_by_run_id:
            self._pending_ops_by_run_id[run_id] = _PendingRunOperations(run_id=run_id)
        return self._pending_ops_by_run_id[run_id]

    def _try_operation(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return e

    def _flush_pending_operations(self, pending_operations):
        """
        Flushes the specified list of pending run operations, blocking on the completion
        of all operations.
        """
        if pending_operations.create_run:
            create_run_tags = pending_operations.create_run.tags
            num_additional_tags_to_include_during_creation = MAX_ENTITIES_PER_BATCH - len(
                create_run_tags
            )
            if num_additional_tags_to_include_during_creation > 0:
                create_run_tags.extend(
                    pending_operations.tags_queue[:num_additional_tags_to_include_during_creation]
                )
                pending_operations.tags_queue = pending_operations.tags_queue[
                    num_additional_tags_to_include_during_creation:
                ]

            new_run = self._client.create_run(
                experiment_id=pending_operations.create_run.experiment_id,
                start_time=pending_operations.create_run.start_time,
                tags={tag.key: tag.value for tag in create_run_tags},
            )
            pending_operations.run_id = new_run.info.run_id

        run_id = pending_operations.run_id
        assert not isinstance(run_id, PendingRunId), "Run ID cannot be pending for logging"

        operation_results = []

        param_batches_to_log = chunk_list(
            pending_operations.params_queue, chunk_size=MAX_PARAMS_TAGS_PER_BATCH,
        )
        tag_batches_to_log = chunk_list(
            pending_operations.tags_queue, chunk_size=MAX_PARAMS_TAGS_PER_BATCH,
        )
        for params_batch, tags_batch in zip_longest(
            param_batches_to_log, tag_batches_to_log, fillvalue=[]
        ):
            metrics_batch_size = min(
                MAX_ENTITIES_PER_BATCH - len(params_batch) - len(tags_batch), MAX_METRICS_PER_BATCH,
            )
            metrics_batch = pending_operations.metrics_queue[:metrics_batch_size]
            pending_operations.metrics_queue = pending_operations.metrics_queue[metrics_batch_size:]

            operation_results.append(
                self._try_operation(
                    self._client.log_batch,
                    run_id=run_id,
                    metrics=metrics_batch,
                    params=params_batch,
                    tags=tags_batch,
                )
            )

        for metrics_batch in chunk_list(
            pending_operations.metrics_queue, chunk_size=MAX_METRICS_PER_BATCH
        ):
            operation_results.append(
                self._try_operation(self._client.log_batch, run_id=run_id, metrics=metrics_batch,)
            )

        if pending_operations.set_terminated:
            operation_results.append(
                self._try_operation(
                    self._client.set_terminated,
                    run_id=run_id,
                    status=pending_operations.set_terminated.status,
                    end_time=pending_operations.set_terminated.end_time,
                )
            )

        failures = [result for result in operation_results if isinstance(result, Exception)]
        if len(failures) > 0:
            raise MlflowException(
                message=(
                    "Failed to perform one or more operations on the run with ID {run_id}."
                    " Failed operations: {failures}".format(run_id=run_id, failures=failures,)
                )
            )


class _PendingRunOperations:
    """
    Represents a collection of queued / pending MLflow Run operations.
    """

    def __init__(self, run_id):
        self.run_id = run_id
        self.create_run = None
        self.set_terminated = None
        self.params_queue = []
        self.tags_queue = []
        self.metrics_queue = []

    def enqueue(self, params=None, tags=None, metrics=None, create_run=None, set_terminated=None):
        """
        Enqueues a new pending logging operation for the associated MLflow Run. 
        """
        if create_run:
            assert not self.create_run, "Attempted to create the same run multiple times"
            self.create_run = create_run
        if set_terminated:
            assert not self.set_terminated, "Attempted to terminate the same run multiple times"
            self.set_terminated = set_terminated

        self.params_queue += params or []
        self.tags_queue += tags or []
        self.metrics_queue += metrics or []


__all__ = [
    "MlflowAutologgingQueueingClient",
]
