import os
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from threading import RLock

from mlflow.entities import Experiment, Run, RunInfo, RunStatus, Param, RunTag, Metric
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
    pass


class _PendingRunOperations:

    def __init__(self, run_id):
        self.run_id = run_id
        self.create_run = None
        self.set_terminated = None
        self.params_queue = []
        self.tags_queue = []
        self.metrics_queue = []

    def add(self, params=None, tags=None, metrics=None, create_run=None, set_terminated=None):
        if create_run:
            self.create_run = create_run
        if set_terminated:
            self.set_terminated = set_terminated

        self.params_queue += (params or [])
        self.tags_queue += (tags or [])
        self.metrics_queue += (metrics or [])


class LoggingOperations:

    def __init__(self, runs_to_futures_map):
        self._runs_to_futures_map = runs_to_futures_map

    def await_completion(self):
        for run_id, future in self._runs_to_futures_map.items():
            future.await_completion()


class AutologgingBatchingClient:
    """
    Efficienty implements a subset of MLflow Tracking's  `MlflowClient` and fluent APIs to provide
    automatic request batching, parallel execution, and parameter / tag truncation for autologging
    use cases.
    """

    def __init__(self):
        self._client = MlflowClient()
        self._pending_ops_by_run_id = {}

        # Limit the number of threads used for logging operations, using at most 8 threads or
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
        Enqueues a CreateRun operation with the specified attributes.
        """
        tags = tags or {}
        tags = _truncate_dict(tags, max_key_length=MAX_ENTITY_KEY_LENGTH, max_value_length=MAX_TAG_VAL_LENGTH)
        run_id = PendingRunId()
        self._get_pending_operations(run_id).add(
            create_run=_PendingCreateRun(
                experiment_id=experiment_id,
                start_time=start_time,
                tags=[RunTag(key, str(value)) for key, value in tags.items()],
            )
        )
        return run_id

    def set_terminated(
        self, run_id: Union[str, PendingRunId], status: Optional[str] = None, end_time: Optional[int] = None
    ) -> None:
        """
        Enqueues an UpdateRun operation with the specified `status` and `end_time` attributes
        for the specified `run_id`.
        """
        self._get_pending_operations(run_id).add(
            set_terminated=_PendingSetTerminated(
                status=status,
                end_time=end_time,
            )
        )

    def log_params(self, run_id: Union[str, PendingRunId], params: Dict[str, Any]) -> None:
        """
        Enqueues a collection of Parameters to be logged to the run specified by `run_id`.
        """
        params = _truncate_dict(params, max_key_length=MAX_ENTITY_KEY_LENGTH, max_value_length=MAX_PARAM_VAL_LENGTH) 
        params_arr = [Param(key, str(value)) for key, value in params.items()]
        self._get_pending_operations(run_id).add(params=params_arr)


    def log_metrics(self, run_id: Union[str, PendingRunId], metrics: Dict[str, float], step: Optional[int] = None) -> None:
        """
        Enqueues a collection of Metrics to be logged to the run specified by `run_id` at the
        step specified by `step`.
        """
        metrics = _truncate_dict(metrics, max_key_length=MAX_ENTITY_KEY_LENGTH) 
        timestamp = int(time.time() * 1000)
        metrics_arr = [Metric(key, value, timestamp, step or 0) for key, value in metrics.items()]
        self._get_pending_operations(run_id).add(metrics=metrics_arr)

    def set_tags(self, run_id: Union[str, PendingRunId], tags: Dict[str, Any]) -> None:
        """
        Enqueues a collection of Tags to be logged to the run specified by `run_id`.
        """
        tags = _truncate_dict(tags, max_key_length=MAX_ENTITY_KEY_LENGTH, max_value_length=MAX_TAG_VAL_LENGTH) 
        tags_arr = [RunTag(key, str(value)) for key, value in tags.items()]
        self._get_pending_operations(run_id).add(tags=tags_arr)

    def flush(self, synchronous=True):
        """
        Flushes all queued logging operations, resulting in the creation or mutation of runs
        and run metadata.

        :param synchronous: If `True`, logging operations are performed synchronously, and a
                            `LoggingOperations` result object is only returned once all operations
                            are complete. If `False`, logging operations are performed
                            asynchronously, and an `LoggingOperations` object is returned that
                            represents the ongoing logging operations.
        :return: A `LoggingOperations` instance.
        """
        runs_to_futures_map = {}
        for pending_operations in self._pending_ops_by_run_id.values():
            future = self._thread_pool.submit(
                self._flush_pending_operations,
                pending_operations=pending_operations,
            )
            runs_to_futures_map[pending_operations.run_id] = future
        self._pending_ops_by_run_id = {}

        logging_ops = LoggingOperations(runs_to_futures_map)
        if synchronous:
            logging_ops.await_completion()
        return logging_ops

    def _get_pending_operations(self, run_id):
        if run_id not in self._pending_ops_by_run_id:
            self._pending_ops_by_run_id[run_id] = _PendingRunOperations(run_id=run_id)
        return self._pending_ops_by_run_id[run_id]

    def _flush_pending_operations(self, pending_operations):
        if pending_operations.create_run:
            create_run_tags = pending_operations.create_run.tags
            num_additional_tags_to_include_during_creation = MAX_ENTITIES_PER_BATCH - len(create_run_tags)
            if num_additional_tags_to_include_during_creation > 0:
                create_run_tags.extend(pending_operations.tags_queue[:num_additional_tags_to_include_during_creation])
                pending_operations.tags_queue = pending_operations.tags_queue[num_additional_tags_to_include_during_creation:]
            
            new_run = self._client.create_run(
                experiment_id=pending_operations.create_run.experiment_id,
                start_time=pending_operations.create_run.start_time,
                tags={
                    tag.key: tag.value
                    for tag in create_run_tags
                },
            )
            pending_operations.run_id = new_run.info.run_id
        
        run_id = pending_operations.run_id
        assert not isinstance(run_id, PendingRunId)

        logging_futures = []

        param_batches_to_log = chunk_list(
            pending_operations.params_queue,
            chunk_size=MAX_PARAMS_TAGS_PER_BATCH,
        )
        tag_batches_to_log = chunk_list(
            pending_operations.tags_queue,
            chunk_size=MAX_PARAMS_TAGS_PER_BATCH,
        )
        for params_batch, tags_batch in zip_longest(
            param_batches_to_log, tag_batches_to_log, fillvalue=[]
        ):
            metrics_batch_size = min(
                MAX_ENTITIES_PER_BATCH - len(params_batch) - len(tags_batch),
                MAX_METRICS_PER_BATCH,
            )
            metrics_batch = pending_operations.metrics_queue[:metrics_batch_size]
            pending_operations.metrics_queue = pending_operations.metrics_queue[metrics_batch_size:]

            logging_futures.append(
                self._thread_pool.submit(
                    self._client.log_batch,
                    run_id=run_id,
                    metrics=metrics_batch,
                    params=params_batch,
                    tags=tags_batch,
                )
            )

        for metrics_batch in chunk_list(pending_operations.metrics_queue, chunk_size=MAX_METRICS_PER_BATCH):
            logging_futures.append(
                self._thread_pool.submit(
                    self._client.log_batch,
                    run_id=run_id,
                    metrics=metrics_batch,
                )
            )

        if pending_operations.set_terminated:
            logging_futures.append(
                self._thread_pool.submit(
                    self._client.set_terminated,
                    run_id=run_id,
                    status=pending_operations.set_terminated.status,
                    end_time=pending_operations.set_terminated.end_time,
                )
            )

        for future in logging_futures:
            future.result()


__all__ = [
    "AutologgingBatchingClient",
]
