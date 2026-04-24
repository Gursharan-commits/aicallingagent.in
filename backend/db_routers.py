class RegionRouter:
    """
    A router to control all database operations on models for different regions.
    Instead of checking model app labels, this router requires context (e.g., thread locals)
    or inspects the `region` attribute if passed directly to the query.
    
    For a fully strict multi-tenant region split, we typically use middleware to extract 
    the Tenant region from the JWT token and set it in a thread-local variable, 
    which this router then reads.
    """
    
    def db_for_read(self, model, **hints):
        """
        Points to the appropriate database for read operations.
        """
        # Example: if a tenant is passed in hints, route to their region
        tenant = hints.get('tenant')
        if tenant:
            region = tenant.region
            if region == 'IN':
                return 'india_db'
            elif region == 'UK':
                return 'uk_db'
        return 'default'

    def db_for_write(self, model, **hints):
        """
        Points to the appropriate database for write operations.
        """
        tenant = hints.get('tenant')
        if tenant:
            region = tenant.region
            if region == 'IN':
                return 'india_db'
            elif region == 'UK':
                return 'uk_db'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations if a model in the same database is involved.
        """
        # Block relations across different region databases
        db1 = self.db_for_read(obj1.__class__, tenant=getattr(obj1, 'tenant', None))
        db2 = self.db_for_read(obj2.__class__, tenant=getattr(obj2, 'tenant', None))
        if db1 == db2:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Ensure migrations run on all databases to keep schemas synced.
        """
        return True
