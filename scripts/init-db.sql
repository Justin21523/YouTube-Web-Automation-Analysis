-- scripts/init-db.sql
-- PostgreSQL Initialization Script
-- YouTube Web Automation Analysis Platform
-- ============================================================================

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Grant privileges to application user
GRANT ALL PRIVILEGES ON DATABASE youtube_automation TO youtube_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO youtube_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO youtube_user;

-- Create indexes for full-text search (will be applied after tables are created)
-- These are placeholder comments for documentation purposes
-- Actual indexes should be created via Alembic migrations

-- ============================================================================
-- Performance Tuning (recommended settings for docker container)
-- ============================================================================
-- These settings should be applied in postgresql.conf or via ALTER SYSTEM

-- Memory settings (adjust based on container memory limit)
-- shared_buffers = 1GB
-- effective_cache_size = 3GB
-- work_mem = 32MB
-- maintenance_work_mem = 256MB

-- Connection settings
-- max_connections = 200
-- idle_in_transaction_session_timeout = 30min

-- Write-ahead log
-- wal_buffers = 64MB
-- checkpoint_completion_target = 0.9

-- Query planning
-- random_page_cost = 1.1
-- effective_io_concurrency = 200

-- Parallel query
-- max_parallel_workers_per_gather = 4
-- max_parallel_workers = 8

-- ============================================================================
-- Monitoring views (optional)
-- ============================================================================

-- View for active connections
CREATE OR REPLACE VIEW pg_active_connections AS
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    query_start,
    state_change,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE state IS NOT NULL;

-- View for table sizes
CREATE OR REPLACE VIEW pg_table_sizes AS
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname || '.' || tablename)) as table_size,
    pg_size_pretty(pg_indexes_size(schemaname || '.' || tablename)) as index_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;

-- View for slow queries (requires pg_stat_statements extension)
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Function to clean old task executions
CREATE OR REPLACE FUNCTION clean_old_task_executions(retention_days INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM task_executions
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL
    AND status IN ('SUCCESS', 'FAILURE');

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Maintenance functions
-- ============================================================================

-- Function to vacuum and analyze all tables
CREATE OR REPLACE FUNCTION maintenance_vacuum_analyze()
RETURNS void AS $$
DECLARE
    table_record RECORD;
BEGIN
    FOR table_record IN
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE 'VACUUM ANALYZE ' ||
                quote_ident(table_record.schemaname) || '.' ||
                quote_ident(table_record.tablename);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Initial data (optional)
-- ============================================================================

-- You can add initial seed data here if needed
-- INSERT INTO ... statements
