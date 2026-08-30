from __future__ import annotations

import ast
import copy
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import time

from redis_om import NotFoundError

import User.EliteBonusService as elite_module
import User.PlacementIncrementalService as placement_module
import User.UserStatsService as user_stats_module
from Common.BonusConfig import ConfigSnapshot
from Common.PeriodResolver import MappingPeriodRepository, PeriodResolver, PeriodSnapshot
from Common.PvAmount import checked_add_int64
from MessageConsumer.PvEventDispatchCoordinator import PvEventDispatchCoordinator
from MessageConsumer.PvEventNormalizer import InMemoryEventRegistry, PvEventNormalizer
from Model.Order.NormalizedPvEvent import NormalizedPvEvent
from Order.ConsumedOrderLedger import InMemoryConsumedOrderLedger
from Order.PvEventDeliveryLedger import DISPATCHED, InMemoryPvEventDeliveryLedger
from Order.RefundReversalLedger import InMemoryRefundReversalLedger
from Redishelper.PVAmountConfigProvider import (
    AR_CONFIG_SOURCE,
    CHECKSUM_FIELD,
    LOAD_MODE_FIELD,
    MANUAL_BOOTSTRAP_MODE,
    READ_FIELD,
    SNAPSHOT_KEY_PREFIX,
    SOURCE_FIELD,
    VERSION_FIELD,
    WRITE_FIELD,
    compute_snapshot_checksum,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


class FakeLock:
    def __init__(self):
        self.acquired = False

    def acquire(self, blocking=True):
        self.acquired = True
        return True

    def owned(self):
        return self.acquired

    def extend(self, _seconds, replace_ttl=True):
        assert replace_ttl is True

    def release(self):
        self.acquired = False


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def watch(self, *keys):
        self.watched = keys

    def exists(self, key):
        return self.redis.exists(key)

    def multi(self):
        return None

    def save_model(self, model):
        self.operations.append(("save", model))

    def set(self, key, value, ex=None):
        self.operations.append(("set", key, value, ex))

    def xadd(self, name, fields, maxlen=None, approximate=None):
        self.operations.append(("xadd", name, fields, maxlen, approximate))

    def execute(self):
        for operation in self.operations:
            if operation[0] == "save":
                operation[1]._persist()
            elif operation[0] == "set":
                _, key, value, _ = operation
                self.redis.values[key] = value
            else:
                self.redis.streams.append(operation)
        self.operations.clear()

    def reset(self):
        self.operations.clear()


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}
        self.streams = []
        self.config_load_count = 0
        self.checksum = compute_snapshot_checksum(
            read_v2=True,
            write_v2=True,
            config_version=1,
            load_mode=MANUAL_BOOTSTRAP_MODE,
            source=AR_CONFIG_SOURCE,
        )

    def eval(self, script, numkeys, *args):
        assert numkeys == 1
        assert "PVAM_LOAD_SNAPSHOT_V1" in script
        self.config_load_count += 1
        return [
            "OK",
            f"1:{self.checksum}",
            f"{SNAPSHOT_KEY_PREFIX}1",
            READ_FIELD,
            "true",
            WRITE_FIELD,
            "true",
            VERSION_FIELD,
            "1",
            LOAD_MODE_FIELD,
            MANUAL_BOOTSTRAP_MODE,
            SOURCE_FIELD,
            AR_CONFIG_SOURCE,
            CHECKSUM_FIELD,
            self.checksum,
        ]

    def exists(self, key):
        return key in self.values

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value

    def lock(self, *args, **kwargs):
        return FakeLock()

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakePipeline(self)

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    def expire(self, key, seconds):
        assert key in self.hashes
        assert seconds > 0


class FakeUserStats:
    records = {}
    redis = None

    def __init__(self, **values):
        defaults = {
            "pv": 0,
            "gpv": 0,
            "gpv_real": 0,
            "gpv_unreal": 0,
            "contrib": 0,
            "is_elite": False,
            "virtual_width": 0,
            "rank": 0,
            "qualified_legs": set(),
            "pv_1l": 0,
            "pv_2l": 0,
            "pre_surplus_1l": 0,
            "pre_surplus_2l": 0,
            "total_1l": 0,
            "total_2l": 0,
            "remain_surplus_1l": 0,
            "remain_surplus_2l": 0,
            "placement_initialized": False,
            "placement_settled": False,
            "placement_revision": 0,
            "settled_revision": 0,
        }
        defaults.update(values)
        self.__dict__.update(defaults)

    @classmethod
    def db(cls):
        return cls.redis

    @classmethod
    def get(cls, record_id):
        try:
            return cls.records[record_id]
        except KeyError as exc:
            raise NotFoundError() from exc

    def save(self, pipeline=None):
        if pipeline is None:
            self._persist()
        else:
            pipeline.save_model(self)

    def _persist(self):
        type(self).records[f"{self.period}:{self.id}"] = self


class FakeEliteBonusStats:
    records = {}

    def __init__(self, **values):
        defaults = {
            "pv_pcs": 0,
            "gpv": 0,
            "gpv_real": 0,
            "contrib_to_parent": 0,
            "qualified_downlines": set(),
            "is_qualified": False,
            "qualifying_path": None,
            "estimated_bonus": 0.0,
            "estimated_bonus_cents": None,
        }
        defaults.update(values)
        self.__dict__.update(defaults)

    @classmethod
    def get(cls, record_id):
        try:
            return cls.records[record_id]
        except KeyError as exc:
            raise NotFoundError() from exc

    def save(self, pipeline=None):
        if pipeline is None:
            self._persist()
        else:
            pipeline.save_model(self)

    def _persist(self):
        type(self).records[self.id] = self


def test_scheme_b_composes_real_three_services_to_dispatched(monkeypatch):
    redis = FakeRedis()
    FakeUserStats.records = {}
    FakeUserStats.redis = redis
    FakeEliteBonusStats.records = {}
    monkeypatch.setattr(user_stats_module, "UserStats", FakeUserStats)
    monkeypatch.setattr(placement_module, "UserStats", FakeUserStats)
    monkeypatch.setattr(elite_module, "EliteBonusStats", FakeEliteBonusStats)

    resolver = PeriodResolver(
        MappingPeriodRepository(
            [
                {"PERIOD_NUM": 40, "CALC_YEAR": 2099, "CALC_MONTH": 5},
                {"PERIOD_NUM": 41, "CALC_YEAR": 2099, "CALC_MONTH": 6},
            ]
        )
    )
    delivery_ledger = InMemoryPvEventDeliveryLedger()
    normalizer = PvEventNormalizer(
        resolver,
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=delivery_ledger,
    )

    user_stats_service = user_stats_module.UserStatsService()
    monkeypatch.setattr(user_stats_service, "_load_ancestors_info", lambda *_: [])
    placement_service = placement_module.PlacementIncrementalService()
    monkeypatch.setattr(placement_service, "_load_placement_ancestors", lambda *_: [])
    elite_bonus_service = elite_module.EliteBonusService(
        period_num=41,
        calc_month=209906,
        config_snapshot=ConfigSnapshot.from_rows(
            [{"config_name": "eliteRate", "type": "bonus", "value": "15"}],
            period_num=41,
            calc_month=209906,
            source="scheme-b-composed-test",
        ),
        dask_address="tcp://unused.invalid:8786",
    )
    elite_bonus_service.redis_conn = redis
    monkeypatch.setattr(elite_bonus_service, "_propagate_upward", lambda **_: None)

    coordinator = PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=user_stats_service,
        placement_service=placement_service,
        elite_bonus_service=elite_bonus_service,
    )

    event = coordinator.dispatch_order(
        {
            "order_id": "O-SCHEME-B-1",
            "period": 41,
            "user_id": "U-1",
            "bv": "1500.99",
        }
    )

    assert delivery_ledger._deliveries[event.identity]["status"] == DISPATCHED
    assert redis.exists("system:idempotency:41:O-SCHEME-B-1:done")
    assert redis.exists("system:idempotency:placement:41:O-SCHEME-B-1:done")
    assert redis.exists("system:idempotency:elite:41:O-SCHEME-B-1:done")
    user_stats = FakeUserStats.records["41:U-1"]
    elite_stats = FakeEliteBonusStats.records["41:U-1"]
    assert user_stats.amount_encoding_version == 2
    assert type(user_stats.pv) is int
    assert user_stats.pv == 1_500_990_000
    assert elite_stats.amount_encoding_version == 2
    assert type(elite_stats.estimated_bonus_cents) is int
    assert elite_stats.estimated_bonus_cents == 22_514
    assert redis.config_load_count == 3


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
