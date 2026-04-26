"""
RegionRouter — routes DB queries to the correct regional shard.

Reads tenant region from the thread-local set by TenantContextMiddleware,
so no explicit `using()` or `hints` kwarg is needed on querysets.

Region → DB alias mapping:
    IN (India)          → india_db   (target: ap-south-1 RDS)
    UK (United Kingdom) → uk_db      (target: eu-west-2 RDS)
    <unset / global>    → default
"""

from apps.tenants.middleware import get_current_region

# Models that always live on the default (global) DB regardless of region.
# Tenants and Users are global because login/auth must resolve before routing.
_GLOBAL_APPS = {"tenants", "users", "auth", "contenttypes", "sessions", "admin"}


def _region_to_db(region: str | None) -> str:
    mapping = {
        "IN": "india_db",
        "UK": "uk_db",
    }
    return mapping.get(region or "", "default")


class RegionRouter:
    """
    Automatic per-request region routing via thread-local tenant context.

    All reads/writes for regional apps (calls, billing, campaigns, ai_engine)
    are directed to the tenant's shard. Global apps stay on 'default'.
    """

    def _target_db(self, app_label: str) -> str:
        if app_label in _GLOBAL_APPS:
            return "default"
        return _region_to_db(get_current_region())

    def db_for_read(self, model, **hints) -> str:
        return self._target_db(model._meta.app_label)

    def db_for_write(self, model, **hints) -> str:
        return self._target_db(model._meta.app_label)

    def allow_relation(self, obj1, obj2, **hints) -> bool | None:
        db1 = self._target_db(obj1.__class__._meta.app_label)
        db2 = self._target_db(obj2.__class__._meta.app_label)
        if db1 == db2:
            return True
        return None  # Django will decide

    def allow_migrate(self, db, app_label, model_name=None, **hints) -> bool:
        # Run migrations on all DBs so schemas stay in sync.
        return True
