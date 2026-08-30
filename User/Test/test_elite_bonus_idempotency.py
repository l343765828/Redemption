import ast
import copy
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import time

from Common.PeriodResolver import PeriodSnapshot
from Common.PvAmount import checked_add_int64
from Model.Order.NormalizedPvEvent import NormalizedPvEvent


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_method(relative_path, class_name, function_name, globals_):
    source_path = REPO_ROOT / relative_path
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    function_node = next(
        copy.deepcopy(node)
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    function_node.decorator_list = []
    function_node.returns = None
    for argument in (
        function_node.args.posonlyargs
        + function_node.args.args
        + function_node.args.kwonlyargs
    ):
        argument.annotation = None
    isolated = ast.Module(body=[function_node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace = dict(globals_)
    exec(compile(isolated, str(source_path), "exec"), namespace)
    return namespace[function_name]


class _Lock:
    def acquire(self):
        return True

    def release(self):
        pass


class _Pipeline:
    def __init__(self, redis_conn):
        self.redis_conn = redis_conn
        self.pending = []

    def set(self, key, value, **_kwargs):
        self.pending.append((key, value))
        return self

    def watch(self, *_keys):
        pass

    def exists(self, key):
        return self.redis_conn.exists(key)

    def multi(self):
        pass

    def reset(self):
        pass

    def execute(self):
        self.redis_conn.pipeline_executions += 1
        self.redis_conn.values.update(self.pending)


class _Redis:
    def __init__(self):
        self.values = {}
        self.pipeline_executions = 0

    def get(self, key):
        return self.values.get(key)

    def exists(self, key):
        return key in self.values

    def lock(self, *_args, **_kwargs):
        return _Lock()

    def pipeline(self, *, transaction):
        assert transaction is True
        return _Pipeline(self)


def _event(identity, pv_delta):
    return NormalizedPvEvent(
        source_event_id=identity,
        user_id="U-1",
        payload_hash="a" * 64,
        business_revision=0,
        previous_business_revision=None,
        effective_pv_delta_units=pv_delta,
        period_snapshot=PeriodSnapshot(
            period_num=40,
            calc_year=None,
            calc_month=None,
            first_period_num=1,
            previous_period_num=39,
            source_checksum="test-period-snapshot",
        ),
        event_kind="REFUND" if pv_delta < 0 else "ORDER",
        original_order_id="O-1" if pv_delta < 0 else None,
    )


def _service(redis_conn, *, current_user=None):
    batch_save = _load_method(
        "User/EliteBonusService.py",
        "EliteBonusService",
        "_batch_save",
        {},
    )
    is_done = _load_method(
        "User/EliteBonusService.py",
        "EliteBonusService",
        "_is_normalized_event_done",
        {},
    )
    service_type = type(
        "_Service",
        (),
        {
            "_batch_save": batch_save,
            "_is_normalized_event_done": staticmethod(is_done),
        },
    )
    service = service_type()
    service.period_num = 40
    service.redis_conn = redis_conn
    if current_user is not None:
        service.get_or_create_calls = 0

        def get_or_create_node(_user_id, _run_config):
            service.get_or_create_calls += 1
            return current_user

        service._get_or_create_node = get_or_create_node
    return service


def _update_method(run_session):
    return _load_method(
        "User/EliteBonusService.py",
        "EliteBonusService",
        "update_elite_bonus_incremental",
        {
            "Any": object,
            "Dict": dict,
            "List": list,
            "Optional": object,
            "PVAmountConfigProvider": lambda redis_conn: redis_conn,
            "PVAmountRunSession": run_session,
            "LOCK_TIMEOUT": 30,
            "LOCK_BLOCKING_TIMEOUT": 5,
            "checked_add_int64": checked_add_int64,
            "json": json,
            "logger": logging.getLogger(__name__),
        },
    )


def test_zero_delta_records_elite_done_key_and_replay_is_noop():
    class NoRunSession:
        @staticmethod
        def start(_provider):
            raise AssertionError("zero delta must not create a business run")

    redis_conn = _Redis()
    service = _service(redis_conn)
    update = _update_method(NoRunSession)
    event = _event("O-ZERO", 0)
    done_key = "system:idempotency:elite:40:O-ZERO:done"

    update(service, user_id="U-1", normalized_event=event)

    assert json.loads(redis_conn.values[done_key]) == {
        "business_revision": 0,
        "identity": "O-ZERO",
        "payload_hash": "a" * 64,
        "period_num": 40,
    }
    assert redis_conn.pipeline_executions == 1

    update(service, user_id="U-1", normalized_event=event)

    assert redis_conn.pipeline_executions == 1


def test_pv_underflow_records_elite_done_key_without_changing_state():
    class RunSession:
        @staticmethod
        def start(_provider):
            return SimpleNamespace(config=object())

    redis_conn = _Redis()
    current_user = SimpleNamespace(pv_pcs=30, gpv=30)
    service = _service(redis_conn, current_user=current_user)
    update = _update_method(RunSession)
    event = _event("R-UNDERFLOW", -50)
    done_key = "system:idempotency:elite:40:R-UNDERFLOW:done"

    update(service, user_id="U-1", normalized_event=event)

    assert json.loads(redis_conn.values[done_key]) == {
        "business_revision": 0,
        "identity": "R-UNDERFLOW",
        "payload_hash": "a" * 64,
        "period_num": 40,
    }
    assert (current_user.pv_pcs, current_user.gpv) == (30, 30)
    assert service.get_or_create_calls == 1
    assert redis_conn.pipeline_executions == 1

    update(service, user_id="U-1", normalized_event=event)

    assert service.get_or_create_calls == 1
    assert redis_conn.pipeline_executions == 1


def test_user_stats_zero_delta_records_done_key_and_replay_is_noop():
    redis_conn = _Redis()

    class UserStatsModel:
        @staticmethod
        def db():
            return redis_conn

    save = _load_method(
        "User/UserStatsService.py",
        "UserStatsService",
        "_save_models_pipeline",
        {
            "Any": object,
            "Dict": dict,
            "List": list,
            "Optional": object,
            "logger": logging.getLogger(__name__),
            "time": time,
        },
    )
    update = _load_method(
        "User/UserStatsService.py",
        "UserStatsService",
        "_update_elite_performance_units",
        {
            "Any": object,
            "Dict": dict,
            "List": list,
            "Optional": object,
            "UserStats": UserStatsModel,
            "json": json,
            "logger": logging.getLogger(__name__),
            "time": time,
        },
    )
    service = type("_UserStatsService", (), {"_save_models_pipeline": save})()
    done_key = "system:idempotency:40:O-ZERO:done"

    update(service, period="40", user_id="U-1", bv=0, order_id="O-ZERO")

    assert json.loads(redis_conn.values[done_key]) | {"done_at": 0} == {
        "period": "40",
        "user_id": "U-1",
        "bv": 0,
        "done_at": 0,
    }
    assert redis_conn.pipeline_executions == 1

    update(service, period="40", user_id="U-1", bv=0, order_id="O-ZERO")

    assert redis_conn.pipeline_executions == 1


def test_placement_zero_delta_records_done_key_and_replay_is_noop():
    redis_conn = _Redis()

    class UserStatsModel:
        @staticmethod
        def db():
            return redis_conn

    redis_module = SimpleNamespace(
        exceptions=SimpleNamespace(
            WatchError=RuntimeError,
            ConnectionError=ConnectionError,
            TimeoutError=TimeoutError,
        )
    )
    save = _load_method(
        "User/PlacementIncrementalService.py",
        "PlacementIncrementalService",
        "_save_placement_pipeline",
        {
            "Any": object,
            "Dict": dict,
            "List": list,
            "json": json,
            "logger": logging.getLogger(__name__),
            "redis": redis_module,
        },
    )
    update = _load_method(
        "User/PlacementIncrementalService.py",
        "PlacementIncrementalService",
        "_update_placement_performance_units",
        {
            "Any": object,
            "Dict": dict,
            "List": list,
            "Optional": object,
            "UserStats": UserStatsModel,
            "logger": logging.getLogger(__name__),
        },
    )
    service_type = type(
        "_PlacementService",
        (),
        {
            "_save_placement_pipeline": save,
            "PERIOD_CLOSED_KEY_TMPL": "period:{period}:closed",
            "GLOBAL_RECALC_LOCK_KEY": "global:recalc:lock",
            "OUTBOX_STREAM_KEY": "placement:outbox",
        },
    )
    service = service_type()
    service._resolve_period_snapshot = lambda _period, snapshot=None: snapshot
    done_key = "system:idempotency:placement:40:O-ZERO:done"

    update(
        service,
        period="40",
        user_id="U-1",
        bv=0,
        order_id="O-ZERO",
        period_snapshot=_event("O-ZERO", 0).period_snapshot,
    )

    assert redis_conn.values[done_key] == "1"
    assert redis_conn.pipeline_executions == 1

    update(
        service,
        period="40",
        user_id="U-1",
        bv=0,
        order_id="O-ZERO",
        period_snapshot=_event("O-ZERO", 0).period_snapshot,
    )

    assert redis_conn.pipeline_executions == 1
