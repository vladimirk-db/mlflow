import shutil
import unittest
import warnings

import sqlalchemy
import time
import mlflow
import uuid

from mlflow.entities import ViewType, RunTag, SourceType, RunStatus, Experiment
from mlflow.protos.service_pb2 import SearchRuns, SearchExpression
from mlflow.store.dbmodels import models
from mlflow import entities
from mlflow.exceptions import MlflowException
from mlflow.store.sqlalchemy_store import SqlAlchemyStore
from mlflow.utils.file_utils import TempDir
from mlflow.utils.search_utils import SearchFilter

DB_URI = 'sqlite://'
ARTIFACT_URI = 'artifact_folder'


class TestSqlAlchemyStoreSqliteInMemory(unittest.TestCase):
    def _setup_database(self, filename=''):
        # use a static file name to initialize sqllite to test retention.
        self.store = SqlAlchemyStore(DB_URI + filename, ARTIFACT_URI)

    def setUp(self):
        self.maxDiff = None  # print all differences on assert failures
        self.store = None
        self._setup_database()

    def tearDown(self):
        if self.store:
            models.Base.metadata.drop_all(self.store.engine)
        shutil.rmtree(ARTIFACT_URI)

    def _experiment_factory(self, names):
        if type(names) is list:
            return [self.store.create_experiment(name=name) for name in names]

        return self.store.create_experiment(name=names)

    def test_default_experiment(self):
        experiments = self.store.list_experiments()
        self.assertEqual(len(experiments), 1)

        first = experiments[0]
        self.assertEqual(first.experiment_id, 0)
        self.assertEqual(first.name, "Default")

    def test_default_experiment_lifecycle(self):
        with TempDir(chdr=True) as tmp:
            tmp_file_name = "sqlite_file_to_lifecycle_test_{}.db".format(int(time.time()))
            self._setup_database("/" + tmp.path(tmp_file_name))

            default_experiment = self.store.get_experiment(experiment_id=0)
            self.assertEqual(default_experiment.name, Experiment.DEFAULT_EXPERIMENT_NAME)
            self.assertEqual(default_experiment.lifecycle_stage, entities.LifecycleStage.ACTIVE)

            self._experiment_factory('aNothEr')
            all_experiments = [e.name for e in self.store.list_experiments()]
            self.assertSequenceEqual(set(['aNothEr', 'Default']), set(all_experiments))

            self.store.delete_experiment(0)

            self.assertSequenceEqual(['aNothEr'], [e.name for e in self.store.list_experiments()])
            another = self.store.get_experiment(1)
            self.assertEqual('aNothEr', another.name)

            default_experiment = self.store.get_experiment(experiment_id=0)
            self.assertEqual(default_experiment.name, Experiment.DEFAULT_EXPERIMENT_NAME)
            self.assertEqual(default_experiment.lifecycle_stage, entities.LifecycleStage.DELETED)

            # destroy SqlStore and make a new one
            del self.store
            self._setup_database("/" + tmp.path(tmp_file_name))

            # test that default experiment is not reactivated
            default_experiment = self.store.get_experiment(experiment_id=0)
            self.assertEqual(default_experiment.name, Experiment.DEFAULT_EXPERIMENT_NAME)
            self.assertEqual(default_experiment.lifecycle_stage, entities.LifecycleStage.DELETED)

            self.assertSequenceEqual(['aNothEr'], [e.name for e in self.store.list_experiments()])
            all_experiments = [e.name for e in self.store.list_experiments(ViewType.ALL)]
            self.assertSequenceEqual(set(['aNothEr', 'Default']), set(all_experiments))

            # ensure that experiment ID dor active experiment is unchanged
            another = self.store.get_experiment(1)
            self.assertEqual('aNothEr', another.name)

            self.store = None

    def test_raise_duplicate_experiments(self):
        with self.assertRaises(Exception):
            self._experiment_factory(['test', 'test'])

    def test_raise_experiment_dont_exist(self):
        with self.assertRaises(Exception):
            self.store.get_experiment(experiment_id=100)

    def test_delete_experiment(self):
        experiments = self._experiment_factory(['morty', 'rick', 'rick and morty'])

        all_experiments = self.store.list_experiments()
        self.assertEqual(len(all_experiments), len(experiments) + 1)  # default

        exp_id = experiments[0]
        self.store.delete_experiment(exp_id)

        updated_exp = self.store.get_experiment(exp_id)
        self.assertEqual(updated_exp.lifecycle_stage, entities.LifecycleStage.DELETED)

        self.assertEqual(len(self.store.list_experiments()), len(all_experiments) - 1)

    def test_get_experiment(self):
        name = 'goku'
        experiment_id = self._experiment_factory(name)
        actual = self.store.get_experiment(experiment_id)
        self.assertEqual(actual.name, name)
        self.assertEqual(actual.experiment_id, experiment_id)

        actual_by_name = self.store.get_experiment_by_name(name)
        self.assertEqual(actual_by_name.name, name)
        self.assertEqual(actual_by_name.experiment_id, experiment_id)

    def test_list_experiments(self):
        testnames = ['blue', 'red', 'green']

        experiments = self._experiment_factory(testnames)
        actual = self.store.list_experiments()

        self.assertEqual(len(experiments) + 1, len(actual))  # default

        with self.store.ManagedSessionMaker() as session:
            for experiment_id in experiments:
                res = session.query(models.SqlExperiment).filter_by(
                    experiment_id=experiment_id).first()
                self.assertIn(res.name, testnames)
                self.assertEqual(res.experiment_id, experiment_id)

    def test_create_experiments(self):
        with self.store.ManagedSessionMaker() as session:
            result = session.query(models.SqlExperiment).all()
            self.assertEqual(len(result), 1)

        experiment_id = self.store.create_experiment(name='test exp')

        with self.store.ManagedSessionMaker() as session:
            result = session.query(models.SqlExperiment).all()
            self.assertEqual(len(result), 2)

            test_exp = session.query(models.SqlExperiment).filter_by(name='test exp').first()
            self.assertEqual(test_exp.experiment_id, experiment_id)
            self.assertEqual(test_exp.name, 'test exp')

        actual = self.store.get_experiment(experiment_id)
        self.assertEqual(actual.experiment_id, experiment_id)
        self.assertEqual(actual.name, 'test exp')

    def test_run_tag_model(self):
        with self.store.ManagedSessionMaker() as session:
            run_data = models.SqlTag(run_uuid='tuuid', key='test', value='val')
            session.add(run_data)
            session.commit()
            tags = session.query(models.SqlTag).all()
            self.assertEqual(len(tags), 1)

            actual = tags[0].to_mlflow_entity()
            self.assertEqual(actual.value, run_data.value)
            self.assertEqual(actual.key, run_data.key)

    def test_metric_model(self):
        with self.store.ManagedSessionMaker() as session:
            run_data = models.SqlMetric(run_uuid='testuid', key='accuracy', value=0.89)
            session.add(run_data)
            session.commit()
            metrics = session.query(models.SqlMetric).all()
            self.assertEqual(len(metrics), 1)

            actual = metrics[0].to_mlflow_entity()
            self.assertEqual(actual.value, run_data.value)
            self.assertEqual(actual.key, run_data.key)

    def test_param_model(self):
        with self.store.ManagedSessionMaker() as session:
            run_data = models.SqlParam(run_uuid='test', key='accuracy', value='test param')
            session.add(run_data)
            session.commit()
            params = session.query(models.SqlParam).all()
            self.assertEqual(len(params), 1)

            actual = params[0].to_mlflow_entity()
            self.assertEqual(actual.value, run_data.value)
            self.assertEqual(actual.key, run_data.key)

    def test_run_needs_uuid(self):
        with self.assertRaises(sqlalchemy.exc.IntegrityError):
            warnings.simplefilter("ignore")
            with self.store.ManagedSessionMaker() as session, warnings.catch_warnings():
                run = models.SqlRun()
                session.add(run)
                warnings.resetwarnings()

    def test_run_data_model(self):
        with self.store.ManagedSessionMaker() as session:
            m1 = models.SqlMetric(key='accuracy', value=0.89)
            m2 = models.SqlMetric(key='recal', value=0.89)
            p1 = models.SqlParam(key='loss', value='test param')
            p2 = models.SqlParam(key='blue', value='test param')

            session.add_all([m1, m2, p1, p2])

            run_data = models.SqlRun(run_uuid=uuid.uuid4().hex)
            run_data.params.append(p1)
            run_data.params.append(p2)
            run_data.metrics.append(m1)
            run_data.metrics.append(m2)

            session.add(run_data)
            session.commit()

            run_datums = session.query(models.SqlRun).all()
            actual = run_datums[0]
            self.assertEqual(len(run_datums), 1)
            self.assertEqual(len(actual.params), 2)
            self.assertEqual(len(actual.metrics), 2)

    def test_run_info(self):
        experiment_id = self._experiment_factory('test exp')
        config = {
            'experiment_id': experiment_id,
            'name': 'test run',
            'user_id': 'Anderson',
            'run_uuid': 'test',
            'status': RunStatus.to_string(RunStatus.SCHEDULED),
            'source_type': SourceType.to_string(SourceType.LOCAL),
            'source_name': 'Python application',
            'entry_point_name': 'main.py',
            'start_time': int(time.time()),
            'end_time': int(time.time()),
            'source_version': mlflow.__version__,
            'lifecycle_stage': entities.LifecycleStage.ACTIVE,
            'artifact_uri': '//'
        }
        run = models.SqlRun(**config).to_mlflow_entity()

        for k, v in config.items():
            v2 = getattr(run.info, k)
            if k == 'source_type':
                self.assertEqual(v, SourceType.to_string(v2))
            elif k == 'status':
                self.assertEqual(v, RunStatus.to_string(v2))
            else:
                self.assertEqual(v, v2)

    def _get_run_configs(self, name='test', experiment_id=None, tags=(), parent_run_id=None):
        return {
            'experiment_id': experiment_id,
            'run_name': name,
            'user_id': 'Anderson',
            'source_type': SourceType.NOTEBOOK,
            'source_name': 'Python application',
            'entry_point_name': 'main.py',
            'start_time': int(time.time()),
            'source_version': mlflow.__version__,
            'tags': tags,
            'parent_run_id': parent_run_id,
        }

    def _run_factory(self, config=None):
        if not config:
            config = self._get_run_configs()

        experiment_id = config.get("experiment_id", None)
        if not experiment_id:
            experiment_id = self._experiment_factory('test exp')
            config["experiment_id"] = experiment_id

        return self.store.create_run(**config)

    def test_create_run_with_tags(self):
        run_name = "test-run-1"
        experiment_id = self._experiment_factory('test_create_run')
        tags = [RunTag('3', '4'), RunTag('1', '2')]
        expected = self._get_run_configs(name=run_name, experiment_id=experiment_id, tags=tags)

        actual = self.store.create_run(**expected)

        self.assertEqual(actual.info.experiment_id, experiment_id)
        self.assertEqual(actual.info.user_id, expected["user_id"])
        self.assertEqual(actual.info.name, run_name)
        self.assertEqual(actual.info.source_type, expected["source_type"])
        self.assertEqual(actual.info.source_name, expected["source_name"])
        self.assertEqual(actual.info.source_version, expected["source_version"])
        self.assertEqual(actual.info.entry_point_name, expected["entry_point_name"])
        self.assertEqual(actual.info.start_time, expected["start_time"])
        
        # Run creation should add an additional tag containing the run name. Check for
        # its existence
        self.assertEqual(len(actual.data.tags), len(tags) + 1)
        name_tag = models.SqlTag(key='mlflow.runName', value=run_name).to_mlflow_entity()
        self.assertListEqual(actual.data.tags, tags + [name_tag])

    def test_create_run_with_parent_id(self):
        run_name = "test-run-1"
        parent_run_id = "parent_uuid_5"
        experiment_id = self._experiment_factory('test_create_run')
        expected = self._get_run_configs(
            name=run_name, experiment_id=experiment_id, parent_run_id=parent_run_id)

        actual = self.store.create_run(**expected)

        self.assertEqual(actual.info.experiment_id, experiment_id)
        self.assertEqual(actual.info.user_id, expected["user_id"])
        self.assertEqual(actual.info.name, run_name)
        self.assertEqual(actual.info.source_type, expected["source_type"])
        self.assertEqual(actual.info.source_name, expected["source_name"])
        self.assertEqual(actual.info.source_version, expected["source_version"])
        self.assertEqual(actual.info.entry_point_name, expected["entry_point_name"])
        self.assertEqual(actual.info.start_time, expected["start_time"])

        # Run creation should add two additional tags containing the run name and parent run id. 
        # Check for the existence of these two tags
        self.assertEqual(len(actual.data.tags), 2)
        name_tag = models.SqlTag(key='mlflow.runName', value=run_name).to_mlflow_entity()
        parent_id_tag = models.SqlTag(key='mlflow.parentRunId',
                                      value=parent_run_id).to_mlflow_entity()
        self.assertListEqual(actual.data.tags, [parent_id_tag, name_tag])

    def test_to_mlflow_entity(self):
        # Create a run and obtain an MLflow Run entity associated with the new run
        run = self._run_factory()

        self.assertIsInstance(run.info, entities.RunInfo)
        self.assertIsInstance(run.data, entities.RunData)

        for metric in run.data.metrics:
            self.assertIsInstance(metric, entities.Metric)

        for param in run.data.params:
            self.assertIsInstance(param, entities.Param)

        for tag in run.data.tags:
            self.assertIsInstance(tag, entities.RunTag)

    def test_delete_run(self):
        run = self._run_factory()

        self.store.delete_run(run.info.run_uuid)

        with self.store.ManagedSessionMaker() as session:
            actual = session.query(models.SqlRun).filter_by(run_uuid=run.info.run_uuid).first()
            self.assertEqual(actual.lifecycle_stage, entities.LifecycleStage.DELETED)

            deleted_run = self.store.get_run(run.info.run_uuid)
            self.assertEqual(actual.run_uuid, deleted_run.info.run_uuid)

    def test_log_metric(self):
        run = self._run_factory()

        tkey = 'blahmetric'
        tval = 100.0
        metric = entities.Metric(tkey, tval, int(time.time()))
        metric2 = entities.Metric(tkey, tval, int(time.time()) + 2)
        self.store.log_metric(run.info.run_uuid, metric)
        self.store.log_metric(run.info.run_uuid, metric2)
    
        run = self.store.get_run(run.info.run_uuid)
        found = False
        for m in run.data.metrics:
            if m.key == tkey and m.value == tval:
                found = True

        self.assertTrue(found)

        # SQL store _get_run method returns full history of recorded metrics.
        # Should return duplicates as well
        # MLflow RunData contains only the last reported values for metrics.
        with self.store.ManagedSessionMaker() as session:
            sql_run_metrics = self.store._get_run(session, run.info.run_uuid).metrics
            self.assertEqual(2, len(sql_run_metrics))
            self.assertEqual(1, len(run.data.metrics))

    def test_log_metric_uniqueness(self):
        run = self._run_factory()

        tkey = 'blahmetric'
        tval = 100.0
        metric = entities.Metric(tkey, tval, int(time.time()))
        metric2 = entities.Metric(tkey, 1.02, int(time.time()))
        self.store.log_metric(run.info.run_uuid, metric)

        with self.assertRaises(MlflowException) as e:
            self.store.log_metric(run.info.run_uuid, metric2)
        self.assertIn("must be unique. Metric already logged value", e.exception.message)

    def test_log_null_metric(self):
        run = self._run_factory()

        tkey = 'blahmetric'
        tval = None
        metric = entities.Metric(tkey, tval, int(time.time()))

        with self.assertRaises(MlflowException) as e:
            self.store.log_metric(run.info.run_uuid, metric)
        self.assertIn("Log metric request failed for run ID=", e.exception.message)
        self.assertIn("IntegrityError", e.exception.message)

    def test_log_param(self):
        run = self._run_factory()

        tkey = 'blahmetric'
        tval = '100.0'
        param = entities.Param(tkey, tval)
        param2 = entities.Param('new param', 'new key')
        self.store.log_param(run.info.run_uuid, param)
        self.store.log_param(run.info.run_uuid, param2)

        run = self.store.get_run(run.info.run_uuid)
        self.assertEqual(2, len(run.data.params))

        found = False
        for m in run.data.params:
            if m.key == tkey and m.value == tval:
                found = True

        self.assertTrue(found)

    def test_log_param_uniqueness(self):
        run = self._run_factory()

        tkey = 'blahmetric'
        tval = '100.0'
        param = entities.Param(tkey, tval)
        param2 = entities.Param(tkey, 'newval')
        self.store.log_param(run.info.run_uuid, param)

        with self.assertRaises(MlflowException) as e:
            self.store.log_param(run.info.run_uuid, param2)
        self.assertIn("Changing param value is not allowed. Param with key=", e.exception.message)

    def test_log_null_param(self):
        run = self._run_factory()

        tkey = 'blahmetric'
        tval = None
        param = entities.Param(tkey, tval)

        with self.assertRaises(MlflowException) as e:
            self.store.log_param(run.info.run_uuid, param)
        self.assertIn("Log param request failed for run ID=", e.exception.message)
        self.assertIn("IntegrityError", e.exception.message)

    def test_set_tag(self):
        run = self._run_factory()

        tkey = 'test tag'
        tval = 'a boogie'
        tag = entities.RunTag(tkey, tval)
        self.store.set_tag(run.info.run_uuid, tag)

        run = self.store.get_run(run.info.run_uuid)

        found = False
        for m in run.data.tags:
            if m.key == tkey and m.value == tval:
                found = True

        self.assertTrue(found)

    def test_get_metric_history(self):
        run = self._run_factory()

        key = 'test'
        expected = [
            models.SqlMetric(key=key, value=0.6, timestamp=1).to_mlflow_entity(),
            models.SqlMetric(key=key, value=0.7, timestamp=2).to_mlflow_entity()
        ]

        for metric in expected:
            self.store.log_metric(run.info.run_uuid, metric)

        actual = self.store.get_metric_history(run.info.run_uuid, key)

        self.assertSequenceEqual([(m.key, m.value, m.timestamp) for m in expected],
                                 [(m.key, m.value, m.timestamp) for m in actual])

    def test_list_run_infos(self):
        experiment_id = self._experiment_factory('test_exp')
        r1 = self._run_factory(config=self._get_run_configs('t1', experiment_id)).info.run_uuid
        r2 = self._run_factory(config=self._get_run_configs('t2', experiment_id)).info.run_uuid

        def _runs(experiment_id, view_type):
            return [r.run_uuid for r in self.store.list_run_infos(experiment_id, view_type)]

        self.assertSequenceEqual([r1, r2], _runs(experiment_id, ViewType.ALL))
        self.assertSequenceEqual([r1, r2], _runs(experiment_id, ViewType.ACTIVE_ONLY))
        self.assertEqual(0, len(_runs(experiment_id, ViewType.DELETED_ONLY)))

        self.store.delete_run(r1)
        self.assertSequenceEqual([r1, r2], _runs(experiment_id, ViewType.ALL))
        self.assertSequenceEqual([r2], _runs(experiment_id, ViewType.ACTIVE_ONLY))
        self.assertSequenceEqual([r1], _runs(experiment_id, ViewType.DELETED_ONLY))

    def test_rename_experiment(self):
        new_name = 'new name'
        experiment_id = self._experiment_factory('test name')
        self.store.rename_experiment(experiment_id, new_name)

        renamed_experiment = self.store.get_experiment(experiment_id)

        self.assertEqual(renamed_experiment.name, new_name)

    def test_update_run_info(self):
        run = self._run_factory()

        new_status = entities.RunStatus.FINISHED
        endtime = int(time.time())

        actual = self.store.update_run_info(run.info.run_uuid, new_status, endtime)

        self.assertEqual(actual.status, new_status)
        self.assertEqual(actual.end_time, endtime)

    def test_restore_experiment(self):
        experiment_id = self._experiment_factory('helloexp')
        exp = self.store.get_experiment(experiment_id)
        self.assertEqual(exp.lifecycle_stage, entities.LifecycleStage.ACTIVE)

        experiment_id = exp.experiment_id
        self.store.delete_experiment(experiment_id)

        deleted = self.store.get_experiment(experiment_id)
        self.assertEqual(deleted.experiment_id, experiment_id)
        self.assertEqual(deleted.lifecycle_stage, entities.LifecycleStage.DELETED)

        self.store.restore_experiment(exp.experiment_id)
        restored = self.store.get_experiment(exp.experiment_id)
        self.assertEqual(restored.experiment_id, experiment_id)
        self.assertEqual(restored.lifecycle_stage, entities.LifecycleStage.ACTIVE)

    def test_delete_restore_run(self):
        run = self._run_factory()
        self.assertEqual(run.info.lifecycle_stage, entities.LifecycleStage.ACTIVE)

        with self.assertRaises(MlflowException) as e:
            self.store.restore_run(run.info.run_uuid)
        self.assertIn("must be in 'deleted' state", e.exception.message)

        self.store.delete_run(run.info.run_uuid)
        with self.assertRaises(MlflowException) as e:
            self.store.delete_run(run.info.run_uuid)
        self.assertIn("must be in 'active' state", e.exception.message)

        deleted = self.store.get_run(run.info.run_uuid)
        self.assertEqual(deleted.info.run_uuid, run.info.run_uuid)
        self.assertEqual(deleted.info.lifecycle_stage, entities.LifecycleStage.DELETED)

        self.store.restore_run(run.info.run_uuid)
        with self.assertRaises(MlflowException) as e:
            self.store.restore_run(run.info.run_uuid)
            self.assertIn("must be in 'deleted' state", e.exception.message)
        restored = self.store.get_run(run.info.run_uuid)
        self.assertEqual(restored.info.run_uuid, run.info.run_uuid)
        self.assertEqual(restored.info.lifecycle_stage, entities.LifecycleStage.ACTIVE)

    def test_error_logging_to_deleted_run(self):
        exp = self._experiment_factory('error_logging')
        run_uuid = self._run_factory(self._get_run_configs(experiment_id=exp)).info.run_uuid

        self.store.delete_run(run_uuid)
        self.assertEqual(self.store.get_run(run_uuid).info.lifecycle_stage,
                         entities.LifecycleStage.DELETED)
        with self.assertRaises(MlflowException) as e:
            self.store.log_param(run_uuid, entities.Param("p1345", "v1"))
        self.assertIn("must be in 'active' state", e.exception.message)

        with self.assertRaises(MlflowException) as e:
            self.store.log_metric(run_uuid, entities.Metric("m1345", 1.0, 123))
        self.assertIn("must be in 'active' state", e.exception.message)

        with self.assertRaises(MlflowException) as e:
            self.store.set_tag(run_uuid, entities.RunTag("t1345", "tv1"))
        self.assertIn("must be in 'active' state", e.exception.message)

        # restore this run and try again
        self.store.restore_run(run_uuid)
        self.assertEqual(self.store.get_run(run_uuid).info.lifecycle_stage,
                         entities.LifecycleStage.ACTIVE)
        self.store.log_param(run_uuid, entities.Param("p1345", "v22"))
        self.store.log_metric(run_uuid, entities.Metric("m1345", 34.0, 85))  # earlier timestamp
        self.store.set_tag(run_uuid, entities.RunTag("t1345", "tv44"))

        run = self.store.get_run(run_uuid)
        assert len(run.data.params) == 1
        p = run.data.params[0]
        self.assertEqual(p.key, "p1345")
        self.assertEqual(p.value, "v22")
        assert len(run.data.metrics) == 1
        m = run.data.metrics[0]
        self.assertEqual(m.key, "m1345")
        self.assertEqual(m.value, 34.0)
        run = self.store.get_run(run_uuid)
        self.assertEqual([("p1345", "v22")],
                         [(p.key, p.value) for p in run.data.params if p.key == "p1345"])
        self.assertEqual([("m1345", 34.0, 85)],
                         [(m.key, m.value, m.timestamp)
                          for m in run.data.metrics if m.key == "m1345"])
        self.assertEqual([("t1345", "tv44")],
                         [(t.key, t.value) for t in run.data.tags if t.key == "t1345"])

    # Tests for Search API
    def _search(self, experiment_id, metrics_expressions=None, param_expressions=None,
                run_view_type=ViewType.ALL):
        search_runs = SearchRuns()
        search_runs.anded_expressions.extend(metrics_expressions or [])
        search_runs.anded_expressions.extend(param_expressions or [])
        search_filter = SearchFilter(search_runs)
        return [r.info.run_uuid
                for r in self.store.search_runs([experiment_id], search_filter, run_view_type)]

    def _param_expression(self, key, comparator, val):
        expr = SearchExpression()
        expr.parameter.key = key
        expr.parameter.string.comparator = comparator
        expr.parameter.string.value = val
        return expr

    def _metric_expression(self, key, comparator, val):
        expr = SearchExpression()
        expr.metric.key = key
        expr.metric.double.comparator = comparator
        expr.metric.double.value = val
        return expr

    def test_search_vanilla(self):
        exp = self._experiment_factory('search_vanilla')
        runs = [self._run_factory(self._get_run_configs('r_%d' % r, exp)).info.run_uuid
                for r in range(3)]

        self.assertSequenceEqual(runs, self._search(exp, run_view_type=ViewType.ALL))
        self.assertSequenceEqual(runs, self._search(exp, run_view_type=ViewType.ACTIVE_ONLY))
        self.assertSequenceEqual([], self._search(exp, run_view_type=ViewType.DELETED_ONLY))

        first = runs[0]

        self.store.delete_run(first)
        self.assertSequenceEqual(runs, self._search(exp, run_view_type=ViewType.ALL))
        self.assertSequenceEqual(runs[1:], self._search(exp, run_view_type=ViewType.ACTIVE_ONLY))
        self.assertSequenceEqual([first], self._search(exp, run_view_type=ViewType.DELETED_ONLY))

        self.store.restore_run(first)
        self.assertSequenceEqual(runs, self._search(exp, run_view_type=ViewType.ALL))
        self.assertSequenceEqual(runs, self._search(exp, run_view_type=ViewType.ACTIVE_ONLY))
        self.assertSequenceEqual([], self._search(exp, run_view_type=ViewType.DELETED_ONLY))

    def test_search_params(self):
        experiment_id = self._experiment_factory('search_params')
        r1 = self._run_factory(self._get_run_configs('r1', experiment_id)).info.run_uuid
        r2 = self._run_factory(self._get_run_configs('r2', experiment_id)).info.run_uuid

        self.store.log_param(r1, entities.Param('generic_param', 'p_val'))
        self.store.log_param(r2, entities.Param('generic_param', 'p_val'))

        self.store.log_param(r1, entities.Param('generic_2', 'some value'))
        self.store.log_param(r2, entities.Param('generic_2', 'another value'))

        self.store.log_param(r1, entities.Param('p_a', 'abc'))
        self.store.log_param(r2, entities.Param('p_b', 'ABC'))

        # test search returns both runs
        expr = self._param_expression("generic_param", "=", "p_val")
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        # test search returns appropriate run (same key different values per run)
        expr = self._param_expression("generic_2", "=", "some value")
        self.assertSequenceEqual([r1], self._search(experiment_id, param_expressions=[expr]))
        expr = self._param_expression("generic_2", "=", "another value")
        self.assertSequenceEqual([r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._param_expression("generic_param", "=", "wrong_val")
        self.assertSequenceEqual([], self._search(experiment_id, param_expressions=[expr]))

        expr = self._param_expression("generic_param", "!=", "p_val")
        self.assertSequenceEqual([], self._search(experiment_id, param_expressions=[expr]))

        expr = self._param_expression("generic_param", "!=", "wrong_val")
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))
        expr = self._param_expression("generic_2", "!=", "wrong_val")
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._param_expression("p_a", "=", "abc")
        self.assertSequenceEqual([r1], self._search(experiment_id, param_expressions=[expr]))

        expr = self._param_expression("p_b", "=", "ABC")
        self.assertSequenceEqual([r2], self._search(experiment_id, param_expressions=[expr]))

    def test_search_metrics(self):
        experiment_id = self._experiment_factory('search_params')
        r1 = self._run_factory(self._get_run_configs('r1', experiment_id)).info.run_uuid
        r2 = self._run_factory(self._get_run_configs('r2', experiment_id)).info.run_uuid

        self.store.log_metric(r1, entities.Metric("common", 1.0, 1))
        self.store.log_metric(r2, entities.Metric("common", 1.0, 1))

        self.store.log_metric(r1, entities.Metric("measure_a", 1.0, 1))
        self.store.log_metric(r2, entities.Metric("measure_a", 200.0, 2))
        self.store.log_metric(r2, entities.Metric("measure_a", 400.0, 3))

        self.store.log_metric(r1, entities.Metric("m_a", 2.0, 2))
        self.store.log_metric(r2, entities.Metric("m_b", 3.0, 2))
        self.store.log_metric(r2, entities.Metric("m_b", 4.0, 8))  # this is last timestamp
        self.store.log_metric(r2, entities.Metric("m_b", 8.0, 3))

        expr = self._metric_expression("common", "=", 1.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("common", ">", 0.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("common", ">=", 0.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("common", "<", 4.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("common", "<=", 4.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("common", "!=", 1.0)
        self.assertSequenceEqual([], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("common", ">=", 3.0)
        self.assertSequenceEqual([], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("common", "<=", 0.75)
        self.assertSequenceEqual([], self._search(experiment_id, param_expressions=[expr]))

        # tests for same metric name across runs with different values and timestamps
        expr = self._metric_expression("measure_a", ">", 0.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("measure_a", "<", 50.0)
        self.assertSequenceEqual([r1], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("measure_a", "<", 1000.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("measure_a", "!=", -12.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("measure_a", ">", 50.0)
        self.assertSequenceEqual([r2], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("measure_a", "=", 1.0)
        self.assertSequenceEqual([r1], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("measure_a", "=", 400.0)
        self.assertSequenceEqual([r2], self._search(experiment_id, param_expressions=[expr]))

        # test search with unique metric keys
        expr = self._metric_expression("m_a", ">", 1.0)
        self.assertSequenceEqual([r1], self._search(experiment_id, param_expressions=[expr]))

        expr = self._metric_expression("m_b", ">", 1.0)
        self.assertSequenceEqual([r2], self._search(experiment_id, param_expressions=[expr]))

        # there is a recorded metric this threshold but not last timestamp
        expr = self._metric_expression("m_b", ">", 5.0)
        self.assertSequenceEqual([], self._search(experiment_id, param_expressions=[expr]))

        # metrics matches last reported timestamp for 'm_b'
        expr = self._metric_expression("m_b", "=", 4.0)
        self.assertSequenceEqual([r2], self._search(experiment_id, param_expressions=[expr]))

    def test_search_full(self):
        experiment_id = self._experiment_factory('search_params')
        r1 = self._run_factory(self._get_run_configs('r1', experiment_id)).info.run_uuid
        r2 = self._run_factory(self._get_run_configs('r2', experiment_id)).info.run_uuid

        self.store.log_param(r1, entities.Param('generic_param', 'p_val'))
        self.store.log_param(r2, entities.Param('generic_param', 'p_val'))

        self.store.log_param(r1, entities.Param('p_a', 'abc'))
        self.store.log_param(r2, entities.Param('p_b', 'ABC'))

        self.store.log_metric(r1, entities.Metric("common", 1.0, 1))
        self.store.log_metric(r2, entities.Metric("common", 1.0, 1))

        self.store.log_metric(r1, entities.Metric("m_a", 2.0, 2))
        self.store.log_metric(r2, entities.Metric("m_b", 3.0, 2))
        self.store.log_metric(r2, entities.Metric("m_b", 4.0, 8))
        self.store.log_metric(r2, entities.Metric("m_b", 8.0, 3))

        p_expr = self._param_expression("generic_param", "=", "p_val")
        m_expr = self._metric_expression("common", "=", 1.0)
        self.assertSequenceEqual([r1, r2], self._search(experiment_id,
                                                        param_expressions=[p_expr],
                                                        metrics_expressions=[m_expr]))

        # all params and metrics match
        p_expr = self._param_expression("generic_param", "=", "p_val")
        m1_expr = self._metric_expression("common", "=", 1.0)
        m2_expr = self._metric_expression("m_a", ">", 1.0)
        self.assertSequenceEqual([r1], self._search(experiment_id,
                                                    param_expressions=[p_expr],
                                                    metrics_expressions=[m1_expr, m2_expr]))

        # test with mismatch param
        p_expr = self._param_expression("random_bad_name", "=", "p_val")
        m1_expr = self._metric_expression("common", "=", 1.0)
        m2_expr = self._metric_expression("m_a", ">", 1.0)
        self.assertSequenceEqual([], self._search(experiment_id,
                                                  param_expressions=[p_expr],
                                                  metrics_expressions=[m1_expr, m2_expr]))

        # test with mismatch metric
        p_expr = self._param_expression("generic_param", "=", "p_val")
        m1_expr = self._metric_expression("common", "=", 1.0)
        m2_expr = self._metric_expression("m_a", ">", 100.0)
        self.assertSequenceEqual([], self._search(experiment_id,
                                                  param_expressions=[p_expr],
                                                  metrics_expressions=[m1_expr, m2_expr]))
