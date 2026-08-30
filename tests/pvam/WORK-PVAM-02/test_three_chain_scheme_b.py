from __future__ import annotations

from redis_om import NotFoundError

import User.EliteBonusService as elite_module
import User.PlacementIncrementalService as placement_module
import User.UserStatsService as user_stats_module
from Common.BonusConfig import ConfigSnapshot
from Common.PeriodResolver import MappingPeriodRepository, PeriodResolver
from MessageConsumer.PvEventDispatchCoordinator import PvEventDispatchCoordinator
from MessageConsumer.PvEventNormalizer import InMemoryEventRegistry, PvEventNormalizer
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
