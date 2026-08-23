-- ============================================================================
-- FinOps Guardian - Complete Setup Script
-- Run top-to-bottom in a Snowflake worksheet as ACCOUNTADMIN.
--
-- Creates every object the Streamlit app depends on:
--   * Core tables (anomalies, audit, savings, notifications)
--   * Agent skill registry + execution trace  (CoCo CLI skills, feedback #2)
--   * Remediation toolkit                     (expanded actions, feedback #4)
--   * Approval tokens + email webhook links   (email approvals, feedback #3)
--   * Detection / remediation procedures, tasks, alerts
-- ============================================================================

CREATE DATABASE IF NOT EXISTS FINOPS_GUARDIAN;
USE DATABASE FINOPS_GUARDIAN;
USE SCHEMA PUBLIC;

-- ============================================================================
-- 1. CONFIGURATION
-- ============================================================================

CREATE TABLE IF NOT EXISTS AGENT_CONFIG (
    CONFIG_KEY   VARCHAR(64) PRIMARY KEY,
    CONFIG_VALUE VARCHAR(1000),
    DESCRIPTION  VARCHAR(500),
    UPDATED_AT   TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

MERGE INTO AGENT_CONFIG t
USING (
    SELECT 'DRY_RUN' AS K,
           'TRUE' AS V,
           'TRUE = log remediation SQL without executing it. Set FALSE to let the agent really ALTER warehouses.' AS D
    UNION ALL SELECT 'APP_URL',
           'https://app.snowflake.com/streamlit/ap-southeast-7.aws/em69097/#/apps/FINOPS_GUARDIAN.PUBLIC.FINOPS_GUARDIAN_APP',
           'Base URL used to build one-click approve/reject links in emails.'
    UNION ALL SELECT 'ALERT_RECIPIENT', '', 'Email address that receives approval requests. Must be a verified Snowflake user email.'
    UNION ALL SELECT 'CREDIT_RATE', '3.00', 'USD per Snowflake credit, used for all dollar figures.'
    UNION ALL SELECT 'TOKEN_TTL_HOURS', '48', 'How long an emailed approve/reject link stays valid.'
) s ON t.CONFIG_KEY = s.K
WHEN NOT MATCHED THEN INSERT (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION) VALUES (s.K, s.V, s.D);

-- ----------------------------------------------------------------------------
-- 1b. Legacy migration
--     Two tables shipped earlier with an incompatible shape:
--       SAVINGS_HISTORY     was (SAVING_ID, SAVED_AT, WAREHOUSE_NAME, CREDITS_SAVED,
--                           ACTION_TYPE) - the dashboard reads SNAPSHOT_DATE and
--                           DOLLAR_SAVED, so the trend chart never rendered.
--       AGENT_EXECUTION_LOG was keyed EXECUTION_ID with no timing columns.
--     Both hold regenerable telemetry, so they are rebuilt rather than patched.
--     Every other table is migrated in place in section 5b.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS SAVINGS_HISTORY;
DROP TABLE IF EXISTS AGENT_EXECUTION_LOG;

-- These two shipped with no arguments and now take a tunable threshold.
-- CREATE OR REPLACE would add an overload rather than replace, and Snowflake
-- rejects that as ambiguous because the new argument has a default.
DROP PROCEDURE IF EXISTS DETECT_OVERSIZED_WAREHOUSE();
DROP PROCEDURE IF EXISTS DETECT_LONG_RUNNING_QUERIES();

-- ============================================================================
-- 2. CORE TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS USAGE_ANOMALIES (
    ANOMALY_ID         NUMBER AUTOINCREMENT PRIMARY KEY,
    WAREHOUSE_NAME     VARCHAR(256) NOT NULL,
    DETECTED_AT        TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    ANOMALY_START      TIMESTAMP_LTZ NOT NULL,
    ANOMALY_END        TIMESTAMP_LTZ,
    ANOMALY_TYPE       VARCHAR(50) NOT NULL,
    SEVERITY           VARCHAR(10) NOT NULL,
    CREDITS_WASTED     NUMBER(38,9) DEFAULT 0,
    DESCRIPTION        VARCHAR(1000),
    SUGGESTED_FIX      VARCHAR(1000),
    STATUS             VARCHAR(20) DEFAULT 'OPEN',
    RESOLVED_AT        TIMESTAMP_LTZ,
    RESOLVED_BY        VARCHAR(256),
    -- Remediation toolkit linkage (feedback #4)
    RECOMMENDED_ACTION VARCHAR(50),
    ACTION_PARAM       VARCHAR(256),
    QUERY_ID           VARCHAR(64),
    DETECTED_BY_SKILL  VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS AUDIT_LOG (
    LOG_ID         NUMBER AUTOINCREMENT PRIMARY KEY,
    LOGGED_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    ACTION_TYPE    VARCHAR(50) NOT NULL,
    ANOMALY_ID     NUMBER,
    WAREHOUSE_NAME VARCHAR(256),
    ACTION_DETAILS VARCHAR(2000) NOT NULL,
    SQL_EXECUTED   VARCHAR(4000),
    APPROVED_BY    VARCHAR(256),
    STATUS         VARCHAR(20) DEFAULT 'COMPLETED',
    ERROR_MESSAGE  VARCHAR(2000),
    APPROVAL_CHANNEL VARCHAR(20) DEFAULT 'UI'   -- UI | EMAIL | AUTO
);

CREATE TABLE IF NOT EXISTS SAVINGS_HISTORY (
    SNAPSHOT_DATE      DATE PRIMARY KEY,
    ANOMALIES_DETECTED NUMBER DEFAULT 0,
    CREDITS_WASTED     NUMBER(38,9) DEFAULT 0,
    CREDITS_SAVED      NUMBER(38,9) DEFAULT 0,
    DOLLAR_SAVED       NUMBER(38,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS NOTIFICATIONS (
    NOTIFICATION_ID   NUMBER AUTOINCREMENT PRIMARY KEY,
    CREATED_AT        TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    NOTIFICATION_TYPE VARCHAR(30) NOT NULL,   -- INFO | WARNING | APPROVAL_NEEDED | APPROVED | REJECTED
    TITLE             VARCHAR(256) NOT NULL,
    MESSAGE           VARCHAR(2000),
    WAREHOUSE_NAME    VARCHAR(256),
    ANOMALY_ID        NUMBER,
    IS_READ           BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS SMART_ALERTS (
    ALERT_ID              NUMBER AUTOINCREMENT PRIMARY KEY,
    NATURAL_LANGUAGE_RULE VARCHAR(1000) NOT NULL,
    PARSED_METRIC         VARCHAR(64),
    PARSED_THRESHOLD      NUMBER(38,4),
    PARSED_WAREHOUSE      VARCHAR(256) DEFAULT 'ANY',
    PARSED_CONDITION      VARCHAR(32) DEFAULT 'greater_than',
    IS_ACTIVE             BOOLEAN DEFAULT TRUE,
    TRIGGER_COUNT         NUMBER DEFAULT 0,
    LAST_TRIGGERED_AT     TIMESTAMP_LTZ,
    CREATED_AT            TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    CREATED_BY            VARCHAR(256) DEFAULT CURRENT_USER()
);

-- ============================================================================
-- 3. AGENT SKILL REGISTRY + EXECUTION TRACE   (feedback #1 and #2)
--    Mirrors the CoCo CLI skills in .snowflake/cortex/skills/. Every detection
--    and remediation run writes its multi-step reasoning here so the UI can
--    stream it and the Intelligence chat can ground answers in it.
-- ============================================================================

CREATE TABLE IF NOT EXISTS AGENT_SKILLS (
    SKILL_NAME     VARCHAR(64) PRIMARY KEY,
    DISPLAY_NAME   VARCHAR(128),
    DESCRIPTION    VARCHAR(1000),
    CATEGORY       VARCHAR(32),      -- DETECTION | REMEDIATION | ANALYSIS
    TRIGGER_TYPE   VARCHAR(32),      -- SCHEDULED | ON_DEMAND | EVENT
    PROCEDURE_NAME VARCHAR(128),
    IS_ENABLED     BOOLEAN DEFAULT TRUE
);

MERGE INTO AGENT_SKILLS t USING (
    SELECT 'cost-anomaly-detector' AS S, 'Cost Anomaly Detector' AS D,
           'Scans warehouse metering for warehouses billing cloud-services credits with zero compute - the signature of a warehouse left running with no work to do.' AS X,
           'DETECTION' AS C, 'SCHEDULED' AS T, 'DETECT_IDLE_COMPUTE_DEMO' AS P
    UNION ALL SELECT 'cost-spike-detector', 'Cost Spike Detector',
           'Compares each hour of credit burn against a trailing 3-hour rolling average and flags multiples above the configured threshold.',
           'DETECTION', 'SCHEDULED', 'DETECT_COST_SPIKE_DEMO'
    UNION ALL SELECT 'warehouse-optimizer', 'Warehouse Optimizer',
           'Measures peak credit draw against provisioned size capacity and recommends a downsize when sustained utilisation stays below 40 percent.',
           'DETECTION', 'SCHEDULED', 'DETECT_OVERSIZED_WAREHOUSE'
    UNION ALL SELECT 'query-watchdog', 'Query Watchdog',
           'Watches for queries exceeding the runtime budget and flags them for cancellation with the owning user and role attached.',
           'DETECTION', 'SCHEDULED', 'DETECT_LONG_RUNNING_QUERIES'
    UNION ALL SELECT 'remediation-engine', 'Remediation Engine',
           'Selects the right action from the remediation toolkit for each open anomaly, auto-applies low-risk fixes and queues high-risk ones for human approval.',
           'REMEDIATION', 'SCHEDULED', 'APPLY_FIXES'
    UNION ALL SELECT 'remediation-approver', 'Remediation Approver',
           'Executes an approved remediation, records who approved it and through which channel (dashboard or one-click email link), and closes the anomaly.',
           'REMEDIATION', 'EVENT', 'APPROVE_FIX'
    UNION ALL SELECT 'alert-evaluator', 'Smart Alert Evaluator',
           'Evaluates natural-language monitoring rules parsed by Cortex against live metering data and raises notifications when a rule trips.',
           'ANALYSIS', 'SCHEDULED', 'EVALUATE_SMART_ALERTS'
) s ON t.SKILL_NAME = s.S
WHEN NOT MATCHED THEN INSERT (SKILL_NAME, DISPLAY_NAME, DESCRIPTION, CATEGORY, TRIGGER_TYPE, PROCEDURE_NAME)
    VALUES (s.S, s.D, s.X, s.C, s.T, s.P);

CREATE TABLE IF NOT EXISTS AGENT_EXECUTION_LOG (
    EXEC_ID          NUMBER AUTOINCREMENT PRIMARY KEY,
    RUN_ID           VARCHAR(36) NOT NULL,
    SKILL_NAME       VARCHAR(64) NOT NULL,
    STEP_NUMBER      NUMBER NOT NULL,
    STEP_DESCRIPTION VARCHAR(1000) NOT NULL,
    RESULT_SUMMARY   VARCHAR(2000),
    STATUS           VARCHAR(20) DEFAULT 'RUNNING',  -- RUNNING | COMPLETED | FAILED | SKIPPED
    EXECUTED_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    COMPLETED_AT     TIMESTAMP_LTZ,
    DURATION_MS      NUMBER,
    ANOMALY_ID       NUMBER,
    TRIGGERED_BY     VARCHAR(256) DEFAULT CURRENT_USER()
);

-- ============================================================================
-- 4. REMEDIATION TOOLKIT   (feedback #4)
--    The agent no longer only sets statement timeouts. Each action is a
--    template the remediation engine binds a warehouse and parameter into.
-- ============================================================================

CREATE TABLE IF NOT EXISTS REMEDIATION_ACTIONS (
    ACTION_CODE       VARCHAR(50) PRIMARY KEY,
    ANOMALY_TYPE      VARCHAR(50) NOT NULL,
    DISPLAY_NAME      VARCHAR(128) NOT NULL,
    DESCRIPTION       VARCHAR(1000),
    SQL_TEMPLATE      VARCHAR(1000) NOT NULL,   -- {WH} and {PARAM} placeholders
    RISK_LEVEL        VARCHAR(10) NOT NULL,     -- LOW | MEDIUM | HIGH
    REQUIRES_APPROVAL BOOLEAN DEFAULT FALSE,
    OWNING_SKILL      VARCHAR(64),
    IS_ENABLED        BOOLEAN DEFAULT TRUE,
    SORT_ORDER        NUMBER DEFAULT 100
);

MERGE INTO REMEDIATION_ACTIONS t USING (
    SELECT 'SET_AUTO_SUSPEND' AS A, 'IDLE_COMPUTE' AS TY, 'Tighten auto-suspend' AS N,
           'Drops AUTO_SUSPEND to 60 seconds so the warehouse parks itself as soon as the query queue drains.' AS D,
           'ALTER WAREHOUSE {WH} SET AUTO_SUSPEND = 60' AS Q,
           'LOW' AS R, FALSE AS AP, 'remediation-engine' AS SK, 10 AS SO
    UNION ALL SELECT 'SUSPEND_WAREHOUSE', 'IDLE_COMPUTE', 'Suspend warehouse now',
           'Immediately suspends a warehouse billing cloud-services credits with no compute running. Auto-resume brings it back on the next query.',
           'ALTER WAREHOUSE {WH} SUSPEND',
           'MEDIUM', FALSE, 'remediation-engine', 20
    UNION ALL SELECT 'ENABLE_AUTO_RESUME', 'IDLE_COMPUTE', 'Enable auto-resume',
           'Turns on AUTO_RESUME so suspending the warehouse cannot strand a workload.',
           'ALTER WAREHOUSE {WH} SET AUTO_RESUME = TRUE',
           'LOW', FALSE, 'remediation-engine', 30
    UNION ALL SELECT 'SET_STATEMENT_TIMEOUT', 'COST_SPIKE', 'Cap statement runtime',
           'Sets STATEMENT_TIMEOUT_IN_SECONDS so a single runaway query cannot burn an unbounded number of credits.',
           'ALTER WAREHOUSE {WH} SET STATEMENT_TIMEOUT_IN_SECONDS = 3600',
           'LOW', FALSE, 'remediation-engine', 40
    UNION ALL SELECT 'SET_RESOURCE_MONITOR', 'COST_SPIKE', 'Attach resource monitor',
           'Binds a credit quota monitor to the warehouse so sustained overspend suspends it rather than billing on.',
           'ALTER WAREHOUSE {WH} SET RESOURCE_MONITOR = {PARAM}',
           'HIGH', TRUE, 'remediation-engine', 50
    UNION ALL SELECT 'SCALE_DOWN_WAREHOUSE', 'OVERSIZED_WAREHOUSE', 'Resize warehouse down',
           'Reduces the warehouse to the smallest size that still covers observed peak demand. Each size step down halves the credit rate.',
           'ALTER WAREHOUSE {WH} SET WAREHOUSE_SIZE = ''{PARAM}''',
           'HIGH', TRUE, 'warehouse-optimizer', 60
    UNION ALL SELECT 'SET_MAX_CLUSTER_COUNT', 'OVERSIZED_WAREHOUSE', 'Cap multi-cluster scale-out',
           'Limits MAX_CLUSTER_COUNT so an over-provisioned multi-cluster warehouse cannot fan out beyond what the workload needs.',
           'ALTER WAREHOUSE {WH} SET MAX_CLUSTER_COUNT = {PARAM}',
           'MEDIUM', TRUE, 'warehouse-optimizer', 70
    UNION ALL SELECT 'CANCEL_QUERY', 'LONG_RUNNING_QUERY', 'Cancel running query',
           'Cancels a specific query that has blown through its runtime budget, releasing the warehouse immediately.',
           'SELECT SYSTEM$CANCEL_QUERY(''{PARAM}'')',
           'HIGH', TRUE, 'query-watchdog', 80
    UNION ALL SELECT 'FLAG_QUERY_FOR_REVIEW', 'LONG_RUNNING_QUERY', 'Flag query for review',
           'Raises a notification naming the query, its owner and its role, without interrupting the workload.',
           '-- FLAG ONLY: query {PARAM} on {WH} raised for human review',
           'LOW', FALSE, 'query-watchdog', 90
) s ON t.ACTION_CODE = s.A
WHEN NOT MATCHED THEN INSERT
    (ACTION_CODE, ANOMALY_TYPE, DISPLAY_NAME, DESCRIPTION, SQL_TEMPLATE, RISK_LEVEL, REQUIRES_APPROVAL, OWNING_SKILL, SORT_ORDER)
    VALUES (s.A, s.TY, s.N, s.D, s.Q, s.R, s.AP, s.SK, s.SO);

-- ============================================================================
-- 5. APPROVAL TOKENS   (feedback #3)
--    Single-use, expiring tokens backing the approve/reject links in email.
-- ============================================================================

CREATE TABLE IF NOT EXISTS APPROVAL_TOKENS (
    TOKEN_ID   VARCHAR(36) PRIMARY KEY,
    ANOMALY_ID NUMBER NOT NULL,
    ACTION     VARCHAR(10) NOT NULL,        -- APPROVE | REJECT
    CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    EXPIRES_AT TIMESTAMP_LTZ NOT NULL,
    USED       BOOLEAN DEFAULT FALSE,
    USED_AT    TIMESTAMP_LTZ,
    USED_BY    VARCHAR(256),
    SENT_TO    VARCHAR(256)
);

-- ----------------------------------------------------------------------------
-- 5b. Bring pre-existing tables up to the current shape.
--     No-ops on a fresh install; on an upgrade they add the columns this
--     release introduced without touching the rows already there.
-- ----------------------------------------------------------------------------
ALTER TABLE USAGE_ANOMALIES ADD COLUMN IF NOT EXISTS RECOMMENDED_ACTION VARCHAR(50);
ALTER TABLE USAGE_ANOMALIES ADD COLUMN IF NOT EXISTS ACTION_PARAM       VARCHAR(256);
ALTER TABLE USAGE_ANOMALIES ADD COLUMN IF NOT EXISTS QUERY_ID           VARCHAR(64);
ALTER TABLE USAGE_ANOMALIES ADD COLUMN IF NOT EXISTS DETECTED_BY_SKILL  VARCHAR(64);

ALTER TABLE AUDIT_LOG       ADD COLUMN IF NOT EXISTS APPROVAL_CHANNEL   VARCHAR(20);

ALTER TABLE NOTIFICATIONS   ADD COLUMN IF NOT EXISTS ANOMALY_ID         NUMBER;

ALTER TABLE SMART_ALERTS    ADD COLUMN IF NOT EXISTS LAST_TRIGGERED_AT  TIMESTAMP_LTZ;
ALTER TABLE SMART_ALERTS    ADD COLUMN IF NOT EXISTS CREATED_BY         VARCHAR(256);

ALTER TABLE APPROVAL_TOKENS ADD COLUMN IF NOT EXISTS USED_AT            TIMESTAMP_LTZ;
ALTER TABLE APPROVAL_TOKENS ADD COLUMN IF NOT EXISTS USED_BY            VARCHAR(256);
ALTER TABLE APPROVAL_TOKENS ADD COLUMN IF NOT EXISTS SENT_TO            VARCHAR(256);

-- Rows detected before the toolkit existed have no action to apply. Give them
-- the same defaults the current detectors would have assigned.
UPDATE USAGE_ANOMALIES
   SET RECOMMENDED_ACTION = CASE ANOMALY_TYPE
           WHEN 'IDLE_COMPUTE'        THEN IFF(CREDITS_WASTED > 0.1, 'SUSPEND_WAREHOUSE', 'SET_AUTO_SUSPEND')
           WHEN 'COST_SPIKE'          THEN 'SET_STATEMENT_TIMEOUT'
           WHEN 'OVERSIZED_WAREHOUSE' THEN 'SCALE_DOWN_WAREHOUSE'
           WHEN 'LONG_RUNNING_QUERY'  THEN 'FLAG_QUERY_FOR_REVIEW'
       END
 WHERE RECOMMENDED_ACTION IS NULL;

UPDATE USAGE_ANOMALIES
   SET DETECTED_BY_SKILL = CASE ANOMALY_TYPE
           WHEN 'IDLE_COMPUTE'        THEN 'cost-anomaly-detector'
           WHEN 'COST_SPIKE'          THEN 'cost-spike-detector'
           WHEN 'OVERSIZED_WAREHOUSE' THEN 'warehouse-optimizer'
           WHEN 'LONG_RUNNING_QUERY'  THEN 'query-watchdog'
       END
 WHERE DETECTED_BY_SKILL IS NULL;

UPDATE AUDIT_LOG SET APPROVAL_CHANNEL = IFF(APPROVED_BY LIKE 'FINOPS_AGENT%', 'AUTO', 'UI')
 WHERE APPROVAL_CHANNEL IS NULL;

-- ============================================================================
-- 6. DEMO DATA
-- ============================================================================

CREATE OR REPLACE TABLE WAREHOUSE_METERING_TEST (
    START_TIME                  TIMESTAMP_LTZ,
    END_TIME                    TIMESTAMP_LTZ,
    WAREHOUSE_ID                NUMBER,
    WAREHOUSE_NAME              VARCHAR(256),
    CREDITS_USED                NUMBER(38,9),
    CREDITS_USED_COMPUTE        NUMBER(38,9),
    CREDITS_USED_CLOUD_SERVICES NUMBER(38,9)
);

-- Hours are generated relative to today so demo data never goes stale.
INSERT INTO WAREHOUSE_METERING_TEST
SELECT
    DATEADD('hour', H, DATE_TRUNC('day', DATEADD('day', -1, CURRENT_TIMESTAMP()))) AS START_TIME,
    DATEADD('hour', H + 1, DATE_TRUNC('day', DATEADD('day', -1, CURRENT_TIMESTAMP()))) AS END_TIME,
    WID, WNAME, CU, CC, CS
FROM (
    -- ANALYTICS_WH: four normal hours, then three idle hours
    SELECT 8 AS H, 100 AS WID, 'ANALYTICS_WH' AS WNAME, 2.100 AS CU, 2.050 AS CC, 0.050 AS CS
    UNION ALL SELECT  9, 100, 'ANALYTICS_WH', 1.900, 1.860, 0.040
    UNION ALL SELECT 10, 100, 'ANALYTICS_WH', 2.300, 2.250, 0.050
    UNION ALL SELECT 11, 100, 'ANALYTICS_WH', 2.000, 1.960, 0.040
    UNION ALL SELECT 12, 100, 'ANALYTICS_WH', 0.050, 0.000, 0.050
    UNION ALL SELECT 13, 100, 'ANALYTICS_WH', 0.048, 0.000, 0.048
    UNION ALL SELECT 14, 100, 'ANALYTICS_WH', 0.052, 0.000, 0.052
    -- ETL_WH: steady baseline then a 4x spike
    UNION ALL SELECT  1, 200, 'ETL_WH', 4.200, 4.100, 0.100
    UNION ALL SELECT  2, 200, 'ETL_WH', 3.800, 3.700, 0.100
    UNION ALL SELECT  3, 200, 'ETL_WH', 4.100, 4.000, 0.100
    UNION ALL SELECT  4, 200, 'ETL_WH', 16.500, 16.200, 0.300
    UNION ALL SELECT  5, 200, 'ETL_WH', 15.800, 15.500, 0.300
    UNION ALL SELECT  6, 200, 'ETL_WH', 4.300, 4.200, 0.100
    -- DEV_WH: left running overnight with no compute
    UNION ALL SELECT 18, 300, 'DEV_WH', 0.120, 0.000, 0.120
    UNION ALL SELECT 19, 300, 'DEV_WH', 0.118, 0.000, 0.118
    UNION ALL SELECT 20, 300, 'DEV_WH', 0.122, 0.000, 0.122
    UNION ALL SELECT 21, 300, 'DEV_WH', 0.115, 0.000, 0.115
    UNION ALL SELECT 22, 300, 'DEV_WH', 0.119, 0.000, 0.119
    UNION ALL SELECT 23, 300, 'DEV_WH', 0.121, 0.000, 0.121
);

-- Provisioned size per demo warehouse, so the optimizer skill has something
-- to compare peak draw against without needing ACCOUNT_USAGE history.
CREATE OR REPLACE TABLE WAREHOUSE_CONFIG_TEST (
    WAREHOUSE_NAME    VARCHAR(256) PRIMARY KEY,
    WAREHOUSE_SIZE    VARCHAR(20),
    CREDITS_PER_HOUR  NUMBER(10,2),   -- capacity at this size
    NEXT_SIZE_DOWN    VARCHAR(20),
    AUTO_SUSPEND_SEC  NUMBER,
    AUTO_RESUME       BOOLEAN
);

INSERT INTO WAREHOUSE_CONFIG_TEST VALUES
    ('ANALYTICS_WH', 'LARGE',   8.0, 'MEDIUM', 900, TRUE),
    ('ETL_WH',       'X-LARGE',16.0, 'LARGE',  300, TRUE),
    ('DEV_WH',       'X-SMALL', 1.0, NULL,     600, TRUE);

-- Synthetic query history for the query-watchdog skill.
CREATE OR REPLACE TABLE QUERY_HISTORY_TEST (
    QUERY_ID           VARCHAR(64),
    WAREHOUSE_NAME     VARCHAR(256),
    USER_NAME          VARCHAR(256),
    ROLE_NAME          VARCHAR(256),
    START_TIME         TIMESTAMP_LTZ,
    TOTAL_ELAPSED_TIME NUMBER,        -- milliseconds
    CREDITS_USED       NUMBER(38,9),
    EXECUTION_STATUS   VARCHAR(30),
    QUERY_TEXT         VARCHAR(2000)
);

INSERT INTO QUERY_HISTORY_TEST
SELECT QID, WH, U, R,
       DATEADD('minute', -MINS_AGO, CURRENT_TIMESTAMP()),
       ELAPSED, CR, STAT, QT
FROM (
    SELECT '01b2c3d4-0000-0001-0000-000000000001' AS QID, 'ETL_WH' AS WH, 'ETL_SERVICE' AS U, 'SYSADMIN' AS R,
           95 AS MINS_AGO, 2760000 AS ELAPSED, 8.400 AS CR, 'RUNNING' AS STAT,
           'INSERT INTO warehouse_fact SELECT * FROM staging.raw_events e JOIN dim_customer c ON e.cust_id = c.id' AS QT
    UNION ALL SELECT '01b2c3d4-0000-0001-0000-000000000002', 'ANALYTICS_WH', 'BI_REPORTER', 'ANALYST',
           40, 1500000, 1.900, 'RUNNING',
           'SELECT * FROM fact_orders o CROSS JOIN dim_date d WHERE o.order_date BETWEEN d.start AND d.end'
    UNION ALL SELECT '01b2c3d4-0000-0001-0000-000000000003', 'ANALYTICS_WH', 'DASHBOARD_SVC', 'ANALYST',
           12, 240000, 0.180, 'SUCCESS',
           'SELECT warehouse_name, SUM(credits_used) FROM metering GROUP BY 1'
    UNION ALL SELECT '01b2c3d4-0000-0001-0000-000000000004', 'DEV_WH', 'DEV_USER', 'DEVELOPER',
           5, 45000, 0.020, 'SUCCESS',
           'SELECT COUNT(*) FROM sandbox.scratch_table'
);

-- ============================================================================
-- 7. AGENT PLUMBING
-- ============================================================================

-- Every skill step is written here as it happens. Statements inside a
-- procedure autocommit, so a second session (the dashboard) sees RUNNING steps
-- while the procedure is still executing - that is what makes the UI trace live.
CREATE OR REPLACE PROCEDURE LOG_AGENT_STEP(
    P_RUN_ID VARCHAR, P_SKILL VARCHAR, P_STEP NUMBER, P_DESC VARCHAR,
    P_RESULT VARCHAR, P_STATUS VARCHAR, P_ANOMALY_ID NUMBER)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    updated NUMBER DEFAULT 0;
BEGIN
    -- A step is opened as RUNNING and closed in place. Keeping one row per
    -- (RUN_ID, STEP_NUMBER) is what lets the dashboard tell a live run from a
    -- finished one, and gives a real elapsed time rather than zero.
    IF (P_STATUS = 'RUNNING') THEN
        INSERT INTO FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG
            (RUN_ID, SKILL_NAME, STEP_NUMBER, STEP_DESCRIPTION, RESULT_SUMMARY, STATUS, ANOMALY_ID)
        SELECT :P_RUN_ID, :P_SKILL, :P_STEP, :P_DESC, :P_RESULT, 'RUNNING', :P_ANOMALY_ID;
        RETURN 'OPENED';
    END IF;

    UPDATE FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG
       SET STATUS           = :P_STATUS,
           STEP_DESCRIPTION = :P_DESC,
           RESULT_SUMMARY   = :P_RESULT,
           COMPLETED_AT     = CURRENT_TIMESTAMP(),
           DURATION_MS      = DATEDIFF('millisecond', EXECUTED_AT, CURRENT_TIMESTAMP()),
           ANOMALY_ID       = COALESCE(:P_ANOMALY_ID, ANOMALY_ID)
     WHERE RUN_ID = :P_RUN_ID AND STEP_NUMBER = :P_STEP;
    updated := SQLROWCOUNT;

    -- Some steps report only their outcome and were never opened.
    IF (updated = 0) THEN
        INSERT INTO FINOPS_GUARDIAN.PUBLIC.AGENT_EXECUTION_LOG
            (RUN_ID, SKILL_NAME, STEP_NUMBER, STEP_DESCRIPTION, RESULT_SUMMARY, STATUS, COMPLETED_AT, DURATION_MS, ANOMALY_ID)
        SELECT :P_RUN_ID, :P_SKILL, :P_STEP, :P_DESC, :P_RESULT, :P_STATUS, CURRENT_TIMESTAMP(), 0, :P_ANOMALY_ID;
    END IF;

    RETURN 'CLOSED';
END;
$$;

CREATE OR REPLACE PROCEDURE NOTIFY(
    P_TYPE VARCHAR, P_TITLE VARCHAR, P_MESSAGE VARCHAR,
    P_WAREHOUSE VARCHAR, P_ANOMALY_ID NUMBER)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.NOTIFICATIONS
        (NOTIFICATION_TYPE, TITLE, MESSAGE, WAREHOUSE_NAME, ANOMALY_ID)
    SELECT :P_TYPE, :P_TITLE, :P_MESSAGE, :P_WAREHOUSE, :P_ANOMALY_ID;
    RETURN 'OK';
END;
$$;

-- ============================================================================
-- 8. DETECTION SKILLS
--    Each returns its RUN_ID so the dashboard can immediately stream the trace.
-- ============================================================================

CREATE OR REPLACE PROCEDURE DETECT_IDLE_COMPUTE_DEMO()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    run_id      VARCHAR DEFAULT UUID_STRING();
    skill       VARCHAR DEFAULT 'cost-anomaly-detector';
    rows_seen   NUMBER DEFAULT 0;
    idle_hours  NUMBER DEFAULT 0;
    inserted    NUMBER DEFAULT 0;
BEGIN
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Load warehouse metering window', NULL, 'RUNNING', NULL);
    SELECT COUNT(*) INTO :rows_seen FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Load warehouse metering window',
        :rows_seen || ' metering rows in scope', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2, 'Isolate hours billing cloud services with zero compute', NULL, 'RUNNING', NULL);
    SELECT COUNT(*) INTO :idle_hours
    FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST
    WHERE CREDITS_USED_COMPUTE = 0 AND CREDITS_USED_CLOUD_SERVICES > 0;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2, 'Isolate hours billing cloud services with zero compute',
        :idle_hours || ' idle warehouse-hours identified', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Score severity, pick remediation and persist new anomalies', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX, RECOMMENDED_ACTION, DETECTED_BY_SKILL
    )
    SELECT
        WAREHOUSE_NAME, START_TIME, END_TIME, 'IDLE_COMPUTE',
        CASE WHEN CREDITS_USED_CLOUD_SERVICES > 1.0 THEN 'HIGH'
             WHEN CREDITS_USED_CLOUD_SERVICES > 0.1 THEN 'MEDIUM'
             ELSE 'LOW' END,
        CREDITS_USED_CLOUD_SERVICES,
        'Warehouse ' || WAREHOUSE_NAME || ' was running but idle from ' ||
            TO_CHAR(START_TIME, 'YYYY-MM-DD HH24:MI') || ' to ' ||
            TO_CHAR(END_TIME, 'YYYY-MM-DD HH24:MI') ||
            '. Cloud services credits consumed with zero compute: ' ||
            ROUND(CREDITS_USED_CLOUD_SERVICES, 6)::VARCHAR,
        'Suspend ' || WAREHOUSE_NAME || ' or tighten its AUTO_SUSPEND window. Idle draw: ' ||
            ROUND(CREDITS_USED_CLOUD_SERVICES, 6)::VARCHAR || ' credits/hour.',
        CASE WHEN CREDITS_USED_CLOUD_SERVICES > 0.1 THEN 'SUSPEND_WAREHOUSE' ELSE 'SET_AUTO_SUSPEND' END,
        'cost-anomaly-detector'
    FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST m
    WHERE m.CREDITS_USED_COMPUTE = 0
      AND m.CREDITS_USED_CLOUD_SERVICES > 0
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.WAREHOUSE_NAME = m.WAREHOUSE_NAME
            AND a.ANOMALY_START = m.START_TIME
            AND a.ANOMALY_TYPE = 'IDLE_COMPUTE');
    inserted := SQLROWCOUNT;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Score severity, pick remediation and persist new anomalies',
        :inserted || ' new anomalies written (' || (:idle_hours - :inserted) || ' already known)', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 4, 'Record scan in audit trail', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION',
           'cost-anomaly-detector scan complete. Idle hours seen: ' || :idle_hours || '. New anomalies: ' || :inserted,
           'COMPLETED';
    IF (inserted > 0) THEN
        CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('WARNING', 'Idle compute detected',
            :inserted || ' warehouse-hours were billing cloud services with no queries running.', NULL, NULL);
    END IF;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 4, 'Record scan in audit trail', 'Audit entry written', 'COMPLETED', NULL);

    RETURN run_id;
END;
$$;

CREATE OR REPLACE PROCEDURE DETECT_COST_SPIKE_DEMO(SPIKE_THRESHOLD FLOAT DEFAULT 2.5)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    run_id   VARCHAR DEFAULT UUID_STRING();
    skill    VARCHAR DEFAULT 'cost-spike-detector';
    inserted NUMBER DEFAULT 0;
    wh_count NUMBER DEFAULT 0;
BEGIN
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Build trailing 3-hour rolling average per warehouse', NULL, 'RUNNING', NULL);
    SELECT COUNT(DISTINCT WAREHOUSE_NAME) INTO :wh_count FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Build trailing 3-hour rolling average per warehouse',
        'Baseline computed for ' || :wh_count || ' warehouses', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2,
        'Flag hours exceeding ' || :SPIKE_THRESHOLD || 'x baseline', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX, RECOMMENDED_ACTION, DETECTED_BY_SKILL
    )
    WITH metering_with_avg AS (
        SELECT WAREHOUSE_NAME, START_TIME, END_TIME, CREDITS_USED,
               AVG(CREDITS_USED) OVER (PARTITION BY WAREHOUSE_NAME ORDER BY START_TIME
                   ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS rolling_avg_3h,
               COUNT(*) OVER (PARTITION BY WAREHOUSE_NAME ORDER BY START_TIME
                   ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS preceding_rows
        FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST
    )
    SELECT
        WAREHOUSE_NAME, START_TIME, END_TIME, 'COST_SPIKE',
        CASE WHEN CREDITS_USED / NULLIF(rolling_avg_3h, 0) > 8.0 THEN 'CRITICAL'
             WHEN CREDITS_USED / NULLIF(rolling_avg_3h, 0) > 4.0 THEN 'HIGH'
             ELSE 'MEDIUM' END,
        CREDITS_USED - rolling_avg_3h,
        'Warehouse ' || WAREHOUSE_NAME || ' cost spike at ' ||
            TO_CHAR(START_TIME, 'YYYY-MM-DD HH24:MI') || '. Used ' ||
            ROUND(CREDITS_USED, 3)::VARCHAR || ' credits vs ' ||
            ROUND(rolling_avg_3h, 3)::VARCHAR || ' rolling average (' ||
            ROUND(CREDITS_USED / NULLIF(rolling_avg_3h, 0), 1)::VARCHAR || 'x normal).',
        'Cap runaway statements on ' || WAREHOUSE_NAME || ' and review QUERY_HISTORY between ' ||
            TO_CHAR(START_TIME, 'HH24:MI') || ' and ' || TO_CHAR(END_TIME, 'HH24:MI') || '.',
        CASE WHEN CREDITS_USED / NULLIF(rolling_avg_3h, 0) > 8.0
             THEN 'SET_RESOURCE_MONITOR' ELSE 'SET_STATEMENT_TIMEOUT' END,
        'cost-spike-detector'
    FROM metering_with_avg m
    WHERE m.preceding_rows >= 2
      AND m.rolling_avg_3h > 0
      AND m.CREDITS_USED / m.rolling_avg_3h >= :SPIKE_THRESHOLD
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.WAREHOUSE_NAME = m.WAREHOUSE_NAME
            AND a.ANOMALY_START = m.START_TIME
            AND a.ANOMALY_TYPE = 'COST_SPIKE');
    inserted := SQLROWCOUNT;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2,
        'Flag hours exceeding ' || :SPIKE_THRESHOLD || 'x baseline',
        :inserted || ' spikes recorded', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Record scan in audit trail', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION',
           'cost-spike-detector scan complete. Threshold: ' || :SPIKE_THRESHOLD || 'x. New anomalies: ' || :inserted,
           'COMPLETED';
    IF (inserted > 0) THEN
        CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('WARNING', 'Cost spike detected',
            :inserted || ' warehouse-hours exceeded ' || :SPIKE_THRESHOLD || 'x their rolling baseline.', NULL, NULL);
    END IF;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Record scan in audit trail', 'Audit entry written', 'COMPLETED', NULL);

    RETURN run_id;
END;
$$;

CREATE OR REPLACE PROCEDURE DETECT_OVERSIZED_WAREHOUSE(UTILISATION_FLOOR FLOAT DEFAULT 0.40)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    run_id   VARCHAR DEFAULT UUID_STRING();
    skill    VARCHAR DEFAULT 'warehouse-optimizer';
    inserted NUMBER DEFAULT 0;
    examined NUMBER DEFAULT 0;
BEGIN
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Read provisioned size and capacity per warehouse', NULL, 'RUNNING', NULL);
    SELECT COUNT(*) INTO :examined FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_CONFIG_TEST WHERE NEXT_SIZE_DOWN IS NOT NULL;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Read provisioned size and capacity per warehouse',
        :examined || ' warehouses eligible for downsizing', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2,
        'Compare peak hourly draw against capacity (floor ' || :UTILISATION_FLOOR || ')', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX, RECOMMENDED_ACTION, ACTION_PARAM, DETECTED_BY_SKILL
    )
    WITH peak AS (
        SELECT m.WAREHOUSE_NAME,
               MAX(m.CREDITS_USED) AS PEAK_CREDITS,
               SUM(m.CREDITS_USED) AS TOTAL_CREDITS,
               MIN(m.START_TIME)   AS WINDOW_START,
               MAX(m.END_TIME)     AS WINDOW_END,
               COUNT(*)            AS HOURS
        FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST m
        GROUP BY m.WAREHOUSE_NAME
    )
    SELECT
        c.WAREHOUSE_NAME, p.WINDOW_START, p.WINDOW_END, 'OVERSIZED_WAREHOUSE',
        CASE WHEN p.PEAK_CREDITS / c.CREDITS_PER_HOUR < 0.20 THEN 'HIGH' ELSE 'MEDIUM' END,
        -- Half the provisioned capacity is reclaimed per size step down.
        ROUND((c.CREDITS_PER_HOUR / 2) * p.HOURS - p.TOTAL_CREDITS, 4),
        'Warehouse ' || c.WAREHOUSE_NAME || ' is provisioned at ' || c.WAREHOUSE_SIZE ||
            ' (' || c.CREDITS_PER_HOUR::VARCHAR || ' credits/hour capacity) but peaked at only ' ||
            ROUND(p.PEAK_CREDITS, 2)::VARCHAR || ' credits/hour - ' ||
            ROUND(100 * p.PEAK_CREDITS / c.CREDITS_PER_HOUR, 0)::VARCHAR || '% utilisation over ' ||
            p.HOURS::VARCHAR || ' metered hours.',
        'Resize ' || c.WAREHOUSE_NAME || ' from ' || c.WAREHOUSE_SIZE || ' to ' || c.NEXT_SIZE_DOWN ||
            ', which still covers observed peak demand and halves the credit rate.',
        'SCALE_DOWN_WAREHOUSE',
        c.NEXT_SIZE_DOWN,
        'warehouse-optimizer'
    FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_CONFIG_TEST c
    JOIN peak p ON p.WAREHOUSE_NAME = c.WAREHOUSE_NAME
    WHERE c.NEXT_SIZE_DOWN IS NOT NULL
      AND p.PEAK_CREDITS / c.CREDITS_PER_HOUR < :UTILISATION_FLOOR
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.WAREHOUSE_NAME = c.WAREHOUSE_NAME
            AND a.ANOMALY_TYPE = 'OVERSIZED_WAREHOUSE'
            AND a.STATUS IN ('OPEN', 'ACKNOWLEDGED'));
    inserted := SQLROWCOUNT;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2,
        'Compare peak hourly draw against capacity (floor ' || :UTILISATION_FLOOR || ')',
        :inserted || ' over-provisioned warehouses found', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Queue downsize recommendations for approval', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION', 'warehouse-optimizer scan complete. Over-provisioned warehouses: ' || :inserted, 'COMPLETED';
    IF (inserted > 0) THEN
        CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('WARNING', 'Over-provisioned warehouse found',
            :inserted || ' warehouse(s) are running a size larger than their peak demand justifies.', NULL, NULL);
    END IF;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Queue downsize recommendations for approval',
        'Recommendations queued', 'COMPLETED', NULL);

    RETURN run_id;
END;
$$;

CREATE OR REPLACE PROCEDURE DETECT_LONG_RUNNING_QUERIES(MAX_RUNTIME_SECONDS NUMBER DEFAULT 600)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    run_id   VARCHAR DEFAULT UUID_STRING();
    skill    VARCHAR DEFAULT 'query-watchdog';
    inserted NUMBER DEFAULT 0;
    scanned  NUMBER DEFAULT 0;
BEGIN
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Scan query history for in-flight and recent statements', NULL, 'RUNNING', NULL);
    SELECT COUNT(*) INTO :scanned FROM FINOPS_GUARDIAN.PUBLIC.QUERY_HISTORY_TEST;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Scan query history for in-flight and recent statements',
        :scanned || ' queries scanned', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2,
        'Flag queries running longer than ' || :MAX_RUNTIME_SECONDS || 's', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX, RECOMMENDED_ACTION, ACTION_PARAM, QUERY_ID, DETECTED_BY_SKILL
    )
    SELECT
        q.WAREHOUSE_NAME, q.START_TIME,
        DATEADD('millisecond', q.TOTAL_ELAPSED_TIME, q.START_TIME), 'LONG_RUNNING_QUERY',
        CASE WHEN q.TOTAL_ELAPSED_TIME / 1000 > 1800 THEN 'HIGH' ELSE 'MEDIUM' END,
        q.CREDITS_USED,
        'Query ' || q.QUERY_ID || ' on ' || q.WAREHOUSE_NAME || ' has run for ' ||
            ROUND(q.TOTAL_ELAPSED_TIME / 60000, 1)::VARCHAR || ' minutes (' ||
            q.EXECUTION_STATUS || '), consuming ' || ROUND(q.CREDITS_USED, 3)::VARCHAR ||
            ' credits. Submitted by ' || q.USER_NAME || ' using role ' || q.ROLE_NAME || '. Statement: ' ||
            LEFT(q.QUERY_TEXT, 200),
        CASE WHEN q.TOTAL_ELAPSED_TIME / 1000 > 1800
             THEN 'Cancel query ' || q.QUERY_ID || ' and ask ' || q.USER_NAME || ' to add a predicate or partition filter.'
             ELSE 'Flag query ' || q.QUERY_ID || ' for review with ' || q.USER_NAME || '; no interruption needed yet.' END,
        CASE WHEN q.TOTAL_ELAPSED_TIME / 1000 > 1800 THEN 'CANCEL_QUERY' ELSE 'FLAG_QUERY_FOR_REVIEW' END,
        q.QUERY_ID,
        q.QUERY_ID,
        'query-watchdog'
    FROM FINOPS_GUARDIAN.PUBLIC.QUERY_HISTORY_TEST q
    WHERE q.TOTAL_ELAPSED_TIME / 1000 > :MAX_RUNTIME_SECONDS
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.QUERY_ID = q.QUERY_ID AND a.ANOMALY_TYPE = 'LONG_RUNNING_QUERY');
    inserted := SQLROWCOUNT;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 2,
        'Flag queries running longer than ' || :MAX_RUNTIME_SECONDS || 's',
        :inserted || ' long-running queries flagged', 'COMPLETED', NULL);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Attribute each query to its user and role', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION', 'query-watchdog scan complete. Runtime budget: ' || :MAX_RUNTIME_SECONDS ||
        's. Queries flagged: ' || :inserted, 'COMPLETED';
    IF (inserted > 0) THEN
        CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('WARNING', 'Long-running queries flagged',
            :inserted || ' queries exceeded the ' || :MAX_RUNTIME_SECONDS || 's runtime budget.', NULL, NULL);
    END IF;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 3, 'Attribute each query to its user and role',
        'Owner and role attached to every finding', 'COMPLETED', NULL);

    RETURN run_id;
END;
$$;

-- Real-account variant of the idle scan, reading ACCOUNT_USAGE instead of demo data.
CREATE OR REPLACE PROCEDURE DETECT_IDLE_COMPUTE(LOOKBACK_HOURS NUMBER DEFAULT 24)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    run_id   VARCHAR DEFAULT UUID_STRING();
    skill    VARCHAR DEFAULT 'cost-anomaly-detector';
    inserted NUMBER DEFAULT 0;
BEGIN
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1,
        'Scan ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY over ' || :LOOKBACK_HOURS || 'h', NULL, 'RUNNING', NULL);
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX, RECOMMENDED_ACTION, DETECTED_BY_SKILL
    )
    SELECT
        h.WAREHOUSE_NAME, h.START_TIME, h.END_TIME, 'IDLE_COMPUTE',
        CASE WHEN h.CREDITS_USED_CLOUD_SERVICES > 1.0 THEN 'HIGH'
             WHEN h.CREDITS_USED_CLOUD_SERVICES > 0.1 THEN 'MEDIUM'
             ELSE 'LOW' END,
        h.CREDITS_USED_CLOUD_SERVICES,
        'Warehouse ' || h.WAREHOUSE_NAME || ' was running but idle from ' ||
            TO_CHAR(h.START_TIME, 'YYYY-MM-DD HH24:MI') || ' to ' ||
            TO_CHAR(h.END_TIME, 'YYYY-MM-DD HH24:MI') || '. Cloud services credits: ' ||
            ROUND(h.CREDITS_USED_CLOUD_SERVICES, 6)::VARCHAR,
        'Suspend ' || h.WAREHOUSE_NAME || ' or tighten AUTO_SUSPEND during off-hours.',
        CASE WHEN h.CREDITS_USED_CLOUD_SERVICES > 0.1 THEN 'SUSPEND_WAREHOUSE' ELSE 'SET_AUTO_SUSPEND' END,
        'cost-anomaly-detector'
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY h
    WHERE h.START_TIME >= DATEADD('hour', -:LOOKBACK_HOURS, CURRENT_TIMESTAMP())
      AND h.CREDITS_USED_COMPUTE = 0
      AND h.CREDITS_USED_CLOUD_SERVICES > 0
      AND h.WAREHOUSE_NAME != 'CLOUD_SERVICES_ONLY'
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.WAREHOUSE_NAME = h.WAREHOUSE_NAME
            AND a.ANOMALY_START = h.START_TIME
            AND a.ANOMALY_TYPE = 'IDLE_COMPUTE');
    inserted := SQLROWCOUNT;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1,
        'Scan ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY over ' || :LOOKBACK_HOURS || 'h',
        :inserted || ' new anomalies written', 'COMPLETED', NULL);

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION', 'Idle compute scan (ACCOUNT_USAGE). Lookback: ' || :LOOKBACK_HOURS ||
        'h. New anomalies: ' || :inserted, 'COMPLETED';
    RETURN run_id;
END;
$$;

-- ============================================================================
-- 9. REMEDIATION ENGINE   (feedback #4)
--    One entry point renders the action template, executes it (or records a
--    dry run), closes the anomaly and writes the audit + trace rows.
-- ============================================================================

CREATE OR REPLACE PROCEDURE EXECUTE_REMEDIATION(
    P_ANOMALY_ID NUMBER, P_ACTION_CODE VARCHAR, P_ACTOR VARCHAR,
    P_CHANNEL VARCHAR, P_RUN_ID VARCHAR, P_STEP NUMBER)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    v_wh        VARCHAR DEFAULT '';
    v_param     VARCHAR DEFAULT '';
    v_type      VARCHAR DEFAULT '';
    v_credits   NUMBER  DEFAULT 0;
    v_template  VARCHAR DEFAULT '';
    v_display   VARCHAR DEFAULT '';
    v_risk      VARCHAR DEFAULT 'LOW';
    v_sql       VARCHAR DEFAULT '';
    v_dry       VARCHAR DEFAULT 'TRUE';
    v_status    VARCHAR DEFAULT 'COMPLETED';
    v_err       VARCHAR DEFAULT NULL;
    v_detail    VARCHAR DEFAULT '';
    v_found     NUMBER  DEFAULT 0;
    v_skill     VARCHAR DEFAULT 'remediation-engine';
BEGIN
    SELECT COUNT(*) INTO :v_found
    FROM FINOPS_GUARDIAN.PUBLIC.REMEDIATION_ACTIONS
    WHERE ACTION_CODE = :P_ACTION_CODE AND IS_ENABLED;
    IF (v_found = 0) THEN
        RETURN 'No enabled remediation action named ' || :P_ACTION_CODE;
    END IF;

    SELECT WAREHOUSE_NAME, COALESCE(ACTION_PARAM, ''), ANOMALY_TYPE, COALESCE(CREDITS_WASTED, 0)
      INTO :v_wh, :v_param, :v_type, :v_credits
      FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
     WHERE ANOMALY_ID = :P_ANOMALY_ID;

    SELECT SQL_TEMPLATE, DISPLAY_NAME, RISK_LEVEL
      INTO :v_template, :v_display, :v_risk
      FROM FINOPS_GUARDIAN.PUBLIC.REMEDIATION_ACTIONS
     WHERE ACTION_CODE = :P_ACTION_CODE;

    SELECT CONFIG_VALUE INTO :v_dry
      FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'DRY_RUN';

    v_sql := REPLACE(REPLACE(:v_template, '{WH}', :v_wh), '{PARAM}', :v_param);

    IF (P_RUN_ID IS NOT NULL) THEN
        CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:P_RUN_ID, :v_skill, :P_STEP,
            'Apply "' || :v_display || '" to ' || :v_wh, NULL, 'RUNNING', :P_ANOMALY_ID);
    END IF;

    -- FLAG_ONLY actions carry no executable SQL.
    IF (STARTSWITH(v_sql, '--')) THEN
        v_status := 'COMPLETED';
        v_detail := :v_display || ' on ' || :v_wh || '. No SQL executed - advisory action.';
    ELSEIF (UPPER(v_dry) = 'TRUE') THEN
        v_status := 'SIMULATED';
        v_detail := :v_display || ' on ' || :v_wh || '. DRY_RUN is TRUE, so the statement was recorded but not executed. '
                 || 'Set AGENT_CONFIG.DRY_RUN = FALSE to let the agent apply it for real.';
    ELSE
        BEGIN
            EXECUTE IMMEDIATE :v_sql;
            v_status := 'COMPLETED';
            v_detail := :v_display || ' applied to ' || :v_wh || '. Estimated recovery: '
                     || ROUND(:v_credits, 4)::VARCHAR || ' credits.';
        EXCEPTION
            WHEN OTHER THEN
                v_status := 'FAILED';
                v_err    := SQLERRM;
                v_detail := :v_display || ' on ' || :v_wh || ' failed: ' || SQLERRM;
        END;
    END IF;

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
        (ACTION_TYPE, ANOMALY_ID, WAREHOUSE_NAME, ACTION_DETAILS, SQL_EXECUTED,
         APPROVED_BY, STATUS, ERROR_MESSAGE, APPROVAL_CHANNEL)
    SELECT
        CASE WHEN :P_CHANNEL = 'AUTO' THEN 'AUTO_ACTION' ELSE 'USER_ACTION' END,
        :P_ANOMALY_ID, :v_wh, :v_detail, :v_sql, :P_ACTOR,
        CASE WHEN :v_status = 'FAILED' THEN 'FAILED' ELSE 'COMPLETED' END,
        :v_err, :P_CHANNEL;

    IF (v_status <> 'FAILED') THEN
        UPDATE FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
           SET STATUS = 'RESOLVED', RESOLVED_AT = CURRENT_TIMESTAMP(), RESOLVED_BY = :P_ACTOR
         WHERE ANOMALY_ID = :P_ANOMALY_ID;
        CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('APPROVED', :v_display || ' applied', :v_detail, :v_wh, :P_ANOMALY_ID);
    ELSE
        CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('WARNING', :v_display || ' failed', :v_detail, :v_wh, :P_ANOMALY_ID);
    END IF;

    IF (P_RUN_ID IS NOT NULL) THEN
        CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:P_RUN_ID, :v_skill, :P_STEP,
            'Apply "' || :v_display || '" to ' || :v_wh, :v_detail,
            CASE WHEN :v_status = 'FAILED' THEN 'FAILED' ELSE 'COMPLETED' END, :P_ANOMALY_ID);
    END IF;

    RETURN :v_status || ': ' || :v_detail;
END;
$$;

CREATE OR REPLACE PROCEDURE APPLY_FIXES()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    run_id      VARCHAR DEFAULT UUID_STRING();
    skill       VARCHAR DEFAULT 'remediation-engine';
    auto_count  NUMBER  DEFAULT 0;
    queued      NUMBER  DEFAULT 0;
    open_count  NUMBER  DEFAULT 0;
    step_no     NUMBER  DEFAULT 2;
    v_sql       VARCHAR;
    v_detail    VARCHAR;
    -- Snowflake Scripting cannot reference rec.COLUMN inside a SQL statement,
    -- only in expressions, so each row is copied into locals first.
    v_id        NUMBER;
    v_wh        VARCHAR;
    v_sev       VARCHAR;
    v_param     VARCHAR;
    v_action    VARCHAR;
    v_template  VARCHAR;
    v_display   VARCHAR;
    v_risk      VARCHAR;
    v_needs_ok  BOOLEAN;
    cur CURSOR FOR
        SELECT a.ANOMALY_ID, a.WAREHOUSE_NAME, a.ANOMALY_TYPE, a.SEVERITY,
               COALESCE(a.ACTION_PARAM, '') AS ACTION_PARAM,
               a.RECOMMENDED_ACTION,
               r.SQL_TEMPLATE, r.DISPLAY_NAME, r.REQUIRES_APPROVAL, r.RISK_LEVEL
        FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
        JOIN FINOPS_GUARDIAN.PUBLIC.REMEDIATION_ACTIONS r
          ON r.ACTION_CODE = a.RECOMMENDED_ACTION AND r.IS_ENABLED
        WHERE a.STATUS = 'OPEN'
        ORDER BY a.ANOMALY_ID;
BEGIN
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Load open anomalies and match each to the remediation toolkit', NULL, 'RUNNING', NULL);
    SELECT COUNT(*) INTO :open_count FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES WHERE STATUS = 'OPEN';
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Load open anomalies and match each to the remediation toolkit',
        :open_count || ' open anomalies to triage', 'COMPLETED', NULL);

    FOR rec IN cur DO
        v_id       := rec.ANOMALY_ID;
        v_wh       := rec.WAREHOUSE_NAME;
        v_sev      := rec.SEVERITY;
        v_param    := rec.ACTION_PARAM;
        v_action   := rec.RECOMMENDED_ACTION;
        v_template := rec.SQL_TEMPLATE;
        v_display  := rec.DISPLAY_NAME;
        v_risk     := rec.RISK_LEVEL;
        v_needs_ok := rec.REQUIRES_APPROVAL;

        IF (v_needs_ok OR v_sev IN ('HIGH', 'CRITICAL')) THEN
            -- Queue for a human. The rendered SQL is stored so the approver
            -- sees exactly what will run, in the UI and in the email.
            v_sql := REPLACE(REPLACE(:v_template, '{WH}', :v_wh), '{PARAM}', :v_param);
            v_detail := :v_display || ' proposed for ' || :v_wh ||
                        ' (' || :v_sev || ' severity, ' || :v_risk || ' risk). Awaiting human approval.';

            UPDATE FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
               SET STATUS = 'ACKNOWLEDGED' WHERE ANOMALY_ID = :v_id;

            INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
                (ACTION_TYPE, ANOMALY_ID, WAREHOUSE_NAME, ACTION_DETAILS, SQL_EXECUTED, STATUS, APPROVAL_CHANNEL)
            SELECT 'RECOMMENDATION', :v_id, :v_wh, :v_detail, :v_sql, 'PENDING_APPROVAL', 'UI';

            CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('APPROVAL_NEEDED', :v_display || ' needs approval', :v_detail, :v_wh, :v_id);
            CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, :step_no,
                'Queue "' || :v_display || '" on ' || :v_wh || ' for approval',
                'Pending human approval - ' || :v_risk || ' risk action', 'COMPLETED', :v_id);
            queued := queued + 1;
        ELSE
            CALL FINOPS_GUARDIAN.PUBLIC.EXECUTE_REMEDIATION(:v_id, :v_action, 'FINOPS_AGENT (auto)', 'AUTO', :run_id, :step_no);
            auto_count := auto_count + 1;
        END IF;
        step_no := step_no + 1;
    END FOR;

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, :step_no, 'Summarise remediation run',
        :auto_count || ' auto-applied, ' || :queued || ' queued for approval', 'COMPLETED', NULL);

    RETURN run_id;
END;
$$;

-- ============================================================================
-- 10. APPROVAL WORKFLOW   (feedback #3)
-- ============================================================================

CREATE OR REPLACE PROCEDURE APPROVE_FIX(
    P_ANOMALY_ID NUMBER, P_APPROVED_BY VARCHAR, P_CHANNEL VARCHAR, P_ACTION_OVERRIDE VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    v_pending NUMBER  DEFAULT 0;
    v_action  VARCHAR DEFAULT NULL;
    run_id    VARCHAR DEFAULT UUID_STRING();
    skill     VARCHAR DEFAULT 'remediation-approver';
BEGIN
    SELECT COUNT(*) INTO :v_pending
      FROM FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
     WHERE ANOMALY_ID = :P_ANOMALY_ID AND STATUS = 'PENDING_APPROVAL';
    IF (v_pending = 0) THEN
        RETURN 'No pending approval found for anomaly ' || :P_ANOMALY_ID;
    END IF;

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1,
        'Validate approval for anomaly #' || :P_ANOMALY_ID, NULL, 'RUNNING', :P_ANOMALY_ID);

    IF (P_ACTION_OVERRIDE IS NOT NULL AND P_ACTION_OVERRIDE <> '') THEN
        v_action := :P_ACTION_OVERRIDE;
        UPDATE FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
           SET RECOMMENDED_ACTION = :P_ACTION_OVERRIDE WHERE ANOMALY_ID = :P_ANOMALY_ID;
    ELSE
        SELECT RECOMMENDED_ACTION INTO :v_action
          FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES WHERE ANOMALY_ID = :P_ANOMALY_ID;
    END IF;

    UPDATE FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
       SET STATUS = 'COMPLETED', APPROVED_BY = :P_APPROVED_BY, APPROVAL_CHANNEL = :P_CHANNEL
     WHERE ANOMALY_ID = :P_ANOMALY_ID AND STATUS = 'PENDING_APPROVAL';

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1,
        'Validate approval for anomaly #' || :P_ANOMALY_ID,
        'Approved by ' || :P_APPROVED_BY || ' via ' || :P_CHANNEL, 'COMPLETED', :P_ANOMALY_ID);

    CALL FINOPS_GUARDIAN.PUBLIC.EXECUTE_REMEDIATION(:P_ANOMALY_ID, :v_action, :P_APPROVED_BY, :P_CHANNEL, :run_id, 2);

    -- Any token still outstanding for this anomaly is now spent.
    UPDATE FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS
       SET USED = TRUE, USED_AT = CURRENT_TIMESTAMP(), USED_BY = :P_APPROVED_BY
     WHERE ANOMALY_ID = :P_ANOMALY_ID AND USED = FALSE;

    RETURN 'Anomaly ' || :P_ANOMALY_ID || ' approved by ' || :P_APPROVED_BY || ' via ' || :P_CHANNEL;
END;
$$;

-- Two-argument form kept so existing callers keep working.
CREATE OR REPLACE PROCEDURE APPROVE_FIX(P_ANOMALY_ID NUMBER, P_APPROVED_BY VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
    CALL FINOPS_GUARDIAN.PUBLIC.APPROVE_FIX(:P_ANOMALY_ID, :P_APPROVED_BY, 'UI', NULL);
    RETURN 'Anomaly ' || :P_ANOMALY_ID || ' approved by ' || :P_APPROVED_BY;
END;
$$;

CREATE OR REPLACE PROCEDURE REJECT_FIX(P_ANOMALY_ID NUMBER, P_REJECTED_BY VARCHAR, P_CHANNEL VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    v_wh   VARCHAR DEFAULT '';
    run_id VARCHAR DEFAULT UUID_STRING();
    skill  VARCHAR DEFAULT 'remediation-approver';
BEGIN
    SELECT WAREHOUSE_NAME INTO :v_wh
      FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES WHERE ANOMALY_ID = :P_ANOMALY_ID;

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1,
        'Reject proposed remediation for anomaly #' || :P_ANOMALY_ID, NULL, 'RUNNING', :P_ANOMALY_ID);

    UPDATE FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
       SET STATUS = 'DISMISSED', RESOLVED_AT = CURRENT_TIMESTAMP(), RESOLVED_BY = :P_REJECTED_BY
     WHERE ANOMALY_ID = :P_ANOMALY_ID;

    UPDATE FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
       SET STATUS = 'COMPLETED', APPROVED_BY = :P_REJECTED_BY, APPROVAL_CHANNEL = :P_CHANNEL,
           ACTION_DETAILS = ACTION_DETAILS || ' [REJECTED by ' || :P_REJECTED_BY || ']'
     WHERE ANOMALY_ID = :P_ANOMALY_ID AND STATUS = 'PENDING_APPROVAL';

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
        (ACTION_TYPE, ANOMALY_ID, WAREHOUSE_NAME, ACTION_DETAILS, APPROVED_BY, STATUS, APPROVAL_CHANNEL)
    SELECT 'USER_ACTION', :P_ANOMALY_ID, :v_wh,
        'Remediation rejected for anomaly ' || :P_ANOMALY_ID || ' by ' || :P_REJECTED_BY,
        :P_REJECTED_BY, 'COMPLETED', :P_CHANNEL;

    UPDATE FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS
       SET USED = TRUE, USED_AT = CURRENT_TIMESTAMP(), USED_BY = :P_REJECTED_BY
     WHERE ANOMALY_ID = :P_ANOMALY_ID AND USED = FALSE;

    CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('REJECTED', 'Remediation rejected',
        'Anomaly ' || :P_ANOMALY_ID || ' on ' || :v_wh || ' was rejected by ' || :P_REJECTED_BY ||
        ' via ' || :P_CHANNEL || '.', :v_wh, :P_ANOMALY_ID);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1,
        'Reject proposed remediation for anomaly #' || :P_ANOMALY_ID,
        'Rejected by ' || :P_REJECTED_BY || ' via ' || :P_CHANNEL, 'COMPLETED', :P_ANOMALY_ID);

    RETURN 'Anomaly ' || :P_ANOMALY_ID || ' rejected by ' || :P_REJECTED_BY;
END;
$$;

CREATE OR REPLACE PROCEDURE GENERATE_APPROVAL_TOKEN(P_ANOMALY_ID NUMBER, P_ACTION VARCHAR, P_SENT_TO VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    v_token VARCHAR DEFAULT UUID_STRING();
    v_ttl   NUMBER  DEFAULT 48;
BEGIN
    SELECT TRY_TO_NUMBER(CONFIG_VALUE) INTO :v_ttl
      FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'TOKEN_TTL_HOURS';
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS
        (TOKEN_ID, ANOMALY_ID, ACTION, EXPIRES_AT, SENT_TO)
    SELECT :v_token, :P_ANOMALY_ID, UPPER(:P_ACTION),
           DATEADD('hour', COALESCE(:v_ttl, 48), CURRENT_TIMESTAMP()), :P_SENT_TO;
    RETURN :v_token;
END;
$$;

-- Redeeming a link runs entirely server-side: the dashboard passes the raw
-- token as a bind parameter and never builds SQL from it.
CREATE OR REPLACE PROCEDURE CONSUME_APPROVAL_TOKEN(P_TOKEN VARCHAR, P_ACTION VARCHAR, P_ACTOR VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    v_rows     NUMBER  DEFAULT 0;
    v_anomaly  NUMBER  DEFAULT 0;
    v_action   VARCHAR DEFAULT '';
    v_used     BOOLEAN DEFAULT FALSE;
    v_expired  NUMBER  DEFAULT 0;
BEGIN
    IF (P_TOKEN IS NULL OR LENGTH(P_TOKEN) <> 36 OR NOT RLIKE(P_TOKEN, '[0-9a-fA-F-]{36}')) THEN
        RETURN 'INVALID: malformed token';
    END IF;

    SELECT COUNT(*) INTO :v_rows FROM FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS WHERE TOKEN_ID = :P_TOKEN;
    IF (v_rows = 0) THEN
        RETURN 'INVALID: unknown token';
    END IF;

    SELECT ANOMALY_ID, ACTION, USED,
           IFF(EXPIRES_AT <= CURRENT_TIMESTAMP(), 1, 0)
      INTO :v_anomaly, :v_action, :v_used, :v_expired
      FROM FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS WHERE TOKEN_ID = :P_TOKEN;

    IF (v_used) THEN
        RETURN 'USED: this link has already been redeemed';
    END IF;
    IF (v_expired = 1) THEN
        RETURN 'EXPIRED: this link is no longer valid';
    END IF;
    IF (UPPER(P_ACTION) <> v_action) THEN
        RETURN 'INVALID: token action mismatch';
    END IF;

    -- Act first, burn the token second. If the remediation throws, the link
    -- stays valid so the reviewer can retry rather than being locked out of a
    -- decision they never actually made. APPROVE_FIX and REJECT_FIX are both
    -- no-ops once the anomaly has left PENDING_APPROVAL, so the ordering
    -- cannot double-apply.
    IF (v_action = 'APPROVE') THEN
        CALL FINOPS_GUARDIAN.PUBLIC.APPROVE_FIX(:v_anomaly, :P_ACTOR, 'EMAIL', NULL);
    ELSE
        CALL FINOPS_GUARDIAN.PUBLIC.REJECT_FIX(:v_anomaly, :P_ACTOR, 'EMAIL');
    END IF;

    UPDATE FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS
       SET USED = TRUE, USED_AT = CURRENT_TIMESTAMP(), USED_BY = :P_ACTOR
     WHERE TOKEN_ID = :P_TOKEN;

    RETURN IFF(:v_action = 'APPROVE', 'APPROVED:', 'REJECTED:') || :v_anomaly;
END;
$$;

-- Builds the approve/reject links and emails them. Returns the two URLs as
-- JSON so the dashboard can show them even when no mail integration exists.
CREATE OR REPLACE PROCEDURE SEND_APPROVAL_EMAIL(P_ANOMALY_ID NUMBER, P_RECIPIENT VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    v_app      VARCHAR DEFAULT '';
    v_base     VARCHAR DEFAULT '';
    v_frag     VARCHAR DEFAULT '';
    v_to       VARCHAR DEFAULT '';
    v_ttl      NUMBER  DEFAULT 48;
    v_approve  VARCHAR DEFAULT UUID_STRING();
    v_reject   VARCHAR DEFAULT UUID_STRING();
    v_url_a    VARCHAR DEFAULT '';
    v_url_r    VARCHAR DEFAULT '';
    v_wh       VARCHAR DEFAULT '';
    v_sev      VARCHAR DEFAULT '';
    v_type     VARCHAR DEFAULT '';
    v_desc     VARCHAR DEFAULT '';
    v_sql      VARCHAR DEFAULT '';
    v_rate     NUMBER  DEFAULT 3.00;
    v_credits  NUMBER  DEFAULT 0;
    v_body     VARCHAR DEFAULT '';
    v_sent     VARCHAR DEFAULT 'NOT_SENT';
BEGIN
    SELECT CONFIG_VALUE INTO :v_app  FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'APP_URL';
    SELECT CONFIG_VALUE INTO :v_to   FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'ALERT_RECIPIENT';
    SELECT TRY_TO_NUMBER(CONFIG_VALUE) INTO :v_ttl  FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'TOKEN_TTL_HOURS';
    SELECT TRY_TO_NUMBER(CONFIG_VALUE) INTO :v_rate FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'CREDIT_RATE';
    IF (P_RECIPIENT IS NOT NULL AND P_RECIPIENT <> '') THEN
        v_to := :P_RECIPIENT;
    END IF;

    SELECT a.WAREHOUSE_NAME, a.SEVERITY, a.ANOMALY_TYPE, a.DESCRIPTION, COALESCE(a.CREDITS_WASTED, 0)
      INTO :v_wh, :v_sev, :v_type, :v_desc, :v_credits
      FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a WHERE a.ANOMALY_ID = :P_ANOMALY_ID;

    SELECT COALESCE(MAX(SQL_EXECUTED), '')
      INTO :v_sql
      FROM FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
     WHERE ANOMALY_ID = :P_ANOMALY_ID AND STATUS = 'PENDING_APPROVAL';

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS (TOKEN_ID, ANOMALY_ID, ACTION, EXPIRES_AT, SENT_TO)
    SELECT :v_approve, :P_ANOMALY_ID, 'APPROVE', DATEADD('hour', COALESCE(:v_ttl, 48), CURRENT_TIMESTAMP()), :v_to
    UNION ALL
    SELECT :v_reject,  :P_ANOMALY_ID, 'REJECT',  DATEADD('hour', COALESCE(:v_ttl, 48), CURRENT_TIMESTAMP()), :v_to;

    -- Query params must sit before the Snowsight fragment to survive the redirect.
    v_base := SPLIT_PART(:v_app, '#', 1);
    v_frag := SPLIT_PART(:v_app, '#', 2);
    -- CHR(38) emits a literal ampersand. Written this way because the
    -- Snowflake CLI reads a bare ampersand-prefixed word in this file as a
    -- SnowSQL template variable when the script is run with -f.
    v_url_a := :v_base || '?token=' || :v_approve || CHR(38) || 'action=approve' || IFF(:v_frag = '', '', '#' || :v_frag);
    v_url_r := :v_base || '?token=' || :v_reject  || CHR(38) || 'action=reject'  || IFF(:v_frag = '', '', '#' || :v_frag);

    v_body :=
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:600px;">' ||
        '<h2 style="color:#1a1a2e;margin-bottom:4px;">FinOps Guardian - approval required</h2>' ||
        '<p style="color:#6B7280;margin-top:0;">Anomaly #' || :P_ANOMALY_ID || ' | ' || :v_type ||
        ' | <strong style="color:#DC2626;">' || :v_sev || '</strong></p>' ||
        '<table style="border-collapse:collapse;width:100%;margin:16px 0;">' ||
        '<tr><td style="padding:6px 0;color:#6B7280;">Warehouse</td><td style="padding:6px 0;"><strong>' || :v_wh || '</strong></td></tr>' ||
        '<tr><td style="padding:6px 0;color:#6B7280;">Credits at risk</td><td style="padding:6px 0;"><strong>' ||
            ROUND(:v_credits, 3)::VARCHAR || ' (~$' || ROUND(:v_credits * COALESCE(:v_rate, 3), 2)::VARCHAR || ')</strong></td></tr>' ||
        '</table>' ||
        '<p style="color:#374151;">' || :v_desc || '</p>' ||
        '<p style="color:#6B7280;margin-bottom:4px;">Proposed remediation:</p>' ||
        '<pre style="background:#F3F4F6;padding:12px;border-radius:8px;font-size:13px;white-space:pre-wrap;">' || :v_sql || '</pre>' ||
        '<p style="margin:24px 0;">' ||
        '<a href="' || :v_url_a || '" style="background:#16A34A;color:#fff;padding:12px 24px;border-radius:8px;' ||
            'text-decoration:none;font-weight:600;margin-right:12px;">Approve and apply</a>' ||
        '<a href="' || :v_url_r || '" style="background:#DC2626;color:#fff;padding:12px 24px;border-radius:8px;' ||
            'text-decoration:none;font-weight:600;">Reject</a>' ||
        '</p>' ||
        '<p style="color:#9CA3AF;font-size:12px;">Each link works once and expires in ' ||
            COALESCE(:v_ttl, 48)::VARCHAR || ' hours. Opening it signs you in to the dashboard, which records ' ||
            'your Snowflake identity against the decision.</p></div>';

    IF (v_to IS NOT NULL AND v_to <> '') THEN
        BEGIN
            CALL SYSTEM$SEND_EMAIL('FINOPS_ALERTS', :v_to,
                '[FinOps Guardian] ' || :v_sev || ' ' || :v_type || ' on ' || :v_wh || ' needs approval',
                :v_body, 'text/html');
            v_sent := 'SENT';
        EXCEPTION
            WHEN OTHER THEN
                v_sent := 'EMAIL_FAILED: ' || SQLERRM;
        END;
    ELSE
        v_sent := 'NO_RECIPIENT: set AGENT_CONFIG.ALERT_RECIPIENT to enable email delivery';
    END IF;

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
        (ACTION_TYPE, ANOMALY_ID, WAREHOUSE_NAME, ACTION_DETAILS, STATUS, APPROVAL_CHANNEL)
    SELECT 'NOTIFICATION', :P_ANOMALY_ID, :v_wh,
        'Approval links generated for anomaly ' || :P_ANOMALY_ID || '. Delivery: ' || :v_sent,
        'COMPLETED', 'EMAIL';

    RETURN OBJECT_CONSTRUCT('status', :v_sent, 'approve_url', :v_url_a, 'reject_url', :v_url_r,
                            'recipient', :v_to, 'expires_hours', COALESCE(:v_ttl, 48))::VARCHAR;
END;
$$;

-- Emails an approval request for every pending anomaly that does not already
-- have a live token outstanding. Used by the HIGH_SEVERITY_ALERT.
CREATE OR REPLACE PROCEDURE SEND_PENDING_APPROVAL_EMAILS()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    sent NUMBER DEFAULT 0;
    v_id NUMBER;
    cur CURSOR FOR
        SELECT DISTINCT a.ANOMALY_ID
        FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
        JOIN FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG l
          ON l.ANOMALY_ID = a.ANOMALY_ID AND l.STATUS = 'PENDING_APPROVAL'
        WHERE a.STATUS = 'ACKNOWLEDGED'
          AND a.SEVERITY IN ('HIGH', 'CRITICAL')
          AND NOT EXISTS (
              SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS t
              WHERE t.ANOMALY_ID = a.ANOMALY_ID
                AND t.USED = FALSE
                AND t.EXPIRES_AT > CURRENT_TIMESTAMP());
BEGIN
    FOR rec IN cur DO
        v_id := rec.ANOMALY_ID;
        CALL FINOPS_GUARDIAN.PUBLIC.SEND_APPROVAL_EMAIL(:v_id, NULL);
        sent := sent + 1;
    END FOR;
    RETURN 'Approval emails dispatched: ' || :sent;
END;
$$;

-- ============================================================================
-- 11. SMART ALERT EVALUATION
-- ============================================================================

CREATE OR REPLACE PROCEDURE EVALUATE_SMART_ALERTS()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    run_id   VARCHAR DEFAULT UUID_STRING();
    skill    VARCHAR DEFAULT 'alert-evaluator';
    rate     NUMBER  DEFAULT 3.00;
    tripped  NUMBER  DEFAULT 0;
    checked  NUMBER  DEFAULT 0;
    v_value  NUMBER  DEFAULT 0;
    v_hit    BOOLEAN DEFAULT FALSE;
    step_no  NUMBER  DEFAULT 2;
    v_id     NUMBER;
    v_rule   VARCHAR;
    v_metric VARCHAR;
    v_thresh NUMBER;
    v_wh     VARCHAR;
    v_cond   VARCHAR;
    cur CURSOR FOR
        SELECT ALERT_ID, NATURAL_LANGUAGE_RULE, PARSED_METRIC, PARSED_THRESHOLD,
               COALESCE(PARSED_WAREHOUSE, 'ANY') AS PARSED_WAREHOUSE, PARSED_CONDITION
        FROM FINOPS_GUARDIAN.PUBLIC.SMART_ALERTS
        WHERE IS_ACTIVE = TRUE;
BEGIN
    SELECT TRY_TO_NUMBER(CONFIG_VALUE) INTO :rate
      FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'CREDIT_RATE';
    rate := COALESCE(:rate, 3.00);

    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Load active natural-language alert rules', NULL, 'RUNNING', NULL);
    SELECT COUNT(*) INTO :checked FROM FINOPS_GUARDIAN.PUBLIC.SMART_ALERTS WHERE IS_ACTIVE = TRUE;
    CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, 1, 'Load active natural-language alert rules',
        :checked || ' active rules', 'COMPLETED', NULL);

    FOR rec IN cur DO
        v_id     := rec.ALERT_ID;
        v_rule   := rec.NATURAL_LANGUAGE_RULE;
        v_metric := rec.PARSED_METRIC;
        v_thresh := rec.PARSED_THRESHOLD;
        v_wh     := rec.PARSED_WAREHOUSE;
        v_cond   := rec.PARSED_CONDITION;

        SELECT COALESCE(MAX(V), 0) INTO :v_value FROM (
            SELECT CASE :v_metric
                WHEN 'daily_spend'      THEN SUM(m.CREDITS_USED) * :rate
                WHEN 'weekly_spend'     THEN SUM(m.CREDITS_USED) * :rate
                WHEN 'credits_per_hour' THEN MAX(m.CREDITS_USED)
                WHEN 'idle_minutes'     THEN 60 * COUNT_IF(m.CREDITS_USED_COMPUTE = 0 AND m.CREDITS_USED_CLOUD_SERVICES > 0)
                ELSE SUM(m.CREDITS_USED) * :rate
            END AS V
            FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST m
            WHERE (:v_wh = 'ANY' OR m.WAREHOUSE_NAME = :v_wh)
            GROUP BY m.WAREHOUSE_NAME
        );

        v_hit := CASE :v_cond
                     WHEN 'greater_than' THEN :v_value >  :v_thresh
                     WHEN 'less_than'    THEN :v_value <  :v_thresh
                     ELSE ABS(:v_value - :v_thresh) < 0.0001
                 END;

        IF (v_hit) THEN
            UPDATE FINOPS_GUARDIAN.PUBLIC.SMART_ALERTS
               SET TRIGGER_COUNT = TRIGGER_COUNT + 1, LAST_TRIGGERED_AT = CURRENT_TIMESTAMP()
             WHERE ALERT_ID = :v_id;
            CALL FINOPS_GUARDIAN.PUBLIC.NOTIFY('WARNING', 'Smart alert triggered',
                'Rule "' || :v_rule || '" tripped: ' || :v_metric ||
                ' reached ' || ROUND(:v_value, 2)::VARCHAR || ' against a threshold of ' ||
                :v_thresh::VARCHAR || '.',
                IFF(:v_wh = 'ANY', NULL, :v_wh), NULL);
            tripped := tripped + 1;
            CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, :step_no,
                'Evaluate rule: ' || LEFT(:v_rule, 120),
                'TRIPPED - ' || :v_metric || ' = ' || ROUND(:v_value, 2)::VARCHAR, 'COMPLETED', NULL);
        ELSE
            CALL FINOPS_GUARDIAN.PUBLIC.LOG_AGENT_STEP(:run_id, :skill, :step_no,
                'Evaluate rule: ' || LEFT(:v_rule, 120),
                'within threshold - ' || :v_metric || ' = ' || ROUND(:v_value, 2)::VARCHAR, 'COMPLETED', NULL);
        END IF;
        step_no := step_no + 1;
    END FOR;

    RETURN 'Evaluated ' || :checked || ' alert rules, ' || :tripped || ' triggered.';
END;
$$;

-- ============================================================================
-- 12. SAVINGS SNAPSHOTS
-- ============================================================================

CREATE OR REPLACE PROCEDURE SNAPSHOT_SAVINGS()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    rate NUMBER DEFAULT 3.00;
BEGIN
    SELECT TRY_TO_NUMBER(CONFIG_VALUE) INTO :rate
      FROM FINOPS_GUARDIAN.PUBLIC.AGENT_CONFIG WHERE CONFIG_KEY = 'CREDIT_RATE';
    rate := COALESCE(:rate, 3.00);

    MERGE INTO FINOPS_GUARDIAN.PUBLIC.SAVINGS_HISTORY t
    USING (
        SELECT CURRENT_DATE() AS D,
               COUNT(*) AS N,
               COALESCE(SUM(CREDITS_WASTED), 0) AS W,
               COALESCE(SUM(CASE WHEN STATUS = 'RESOLVED' THEN CREDITS_WASTED ELSE 0 END), 0) AS S
        FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
    ) s ON t.SNAPSHOT_DATE = s.D
    WHEN MATCHED THEN UPDATE SET
        ANOMALIES_DETECTED = s.N, CREDITS_WASTED = s.W,
        CREDITS_SAVED = s.S, DOLLAR_SAVED = ROUND(s.S * :rate, 2)
    WHEN NOT MATCHED THEN INSERT
        (SNAPSHOT_DATE, ANOMALIES_DETECTED, CREDITS_WASTED, CREDITS_SAVED, DOLLAR_SAVED)
        VALUES (s.D, s.N, s.W, s.S, ROUND(s.S * :rate, 2));

    RETURN 'Savings snapshot written for ' || CURRENT_DATE()::VARCHAR;
END;
$$;

-- ============================================================================
-- 13. STAGE, STREAMLIT APP, EMAIL INTEGRATION
-- ============================================================================

CREATE STAGE IF NOT EXISTS STREAMLIT_STAGE
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- Upload the app before creating the Streamlit object:
--   PUT 'file://./streamlit_app.py' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
--   PUT 'file://./.streamlit/config.toml' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/.streamlit/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- IF NOT EXISTS, never OR REPLACE: replacing a Streamlit object rotates its
-- url_id, which changes the app URL and invalidates every approval link
-- already sitting in someone's inbox.
CREATE STREAMLIT IF NOT EXISTS FINOPS_GUARDIAN_APP
    ROOT_LOCATION = '@FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE'
    MAIN_FILE = 'streamlit_app.py'
    QUERY_WAREHOUSE = COMPUTE_WH
    TITLE = 'FinOps Guardian';

-- Email channel for approval requests. ALLOWED_RECIPIENTS must list verified
-- Snowflake user emails; replace with your own before running.
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS FINOPS_ALERTS
    TYPE = EMAIL
    ENABLED = TRUE;

-- ============================================================================
-- 14. SCHEDULED MONITORING
--     Detection fans out hourly, remediation runs after it, then alerts and
--     the savings snapshot. All tasks are created SUSPENDED - resume them
--     explicitly (see README) so an install never starts billing by surprise.
-- ============================================================================

CREATE OR REPLACE TASK TASK_DETECT_IDLE
    WAREHOUSE = COMPUTE_WH
    SCHEDULE = 'USING CRON 0 * * * * UTC'
AS CALL FINOPS_GUARDIAN.PUBLIC.DETECT_IDLE_COMPUTE_DEMO();

CREATE OR REPLACE TASK TASK_DETECT_SPIKE
    WAREHOUSE = COMPUTE_WH
    AFTER TASK_DETECT_IDLE
AS CALL FINOPS_GUARDIAN.PUBLIC.DETECT_COST_SPIKE_DEMO(2.5);

CREATE OR REPLACE TASK TASK_DETECT_OVERSIZED
    WAREHOUSE = COMPUTE_WH
    AFTER TASK_DETECT_SPIKE
AS CALL FINOPS_GUARDIAN.PUBLIC.DETECT_OVERSIZED_WAREHOUSE(0.40);

CREATE OR REPLACE TASK TASK_DETECT_LONG_QUERIES
    WAREHOUSE = COMPUTE_WH
    AFTER TASK_DETECT_OVERSIZED
AS CALL FINOPS_GUARDIAN.PUBLIC.DETECT_LONG_RUNNING_QUERIES(600);

CREATE OR REPLACE TASK TASK_APPLY_FIXES
    WAREHOUSE = COMPUTE_WH
    AFTER TASK_DETECT_LONG_QUERIES
AS CALL FINOPS_GUARDIAN.PUBLIC.APPLY_FIXES();

CREATE OR REPLACE TASK TASK_EVALUATE_ALERTS
    WAREHOUSE = COMPUTE_WH
    AFTER TASK_APPLY_FIXES
AS CALL FINOPS_GUARDIAN.PUBLIC.EVALUATE_SMART_ALERTS();

CREATE OR REPLACE TASK TASK_SNAPSHOT_SAVINGS
    WAREHOUSE = COMPUTE_WH
    AFTER TASK_EVALUATE_ALERTS
AS CALL FINOPS_GUARDIAN.PUBLIC.SNAPSHOT_SAVINGS();

-- Emails one-click approve/reject links whenever a HIGH or CRITICAL
-- remediation is waiting on a human.
CREATE OR REPLACE ALERT HIGH_SEVERITY_ALERT
    WAREHOUSE = COMPUTE_WH
    SCHEDULE = '15 MINUTE'
    IF (EXISTS (
        SELECT 1
        FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
        JOIN FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG l
          ON l.ANOMALY_ID = a.ANOMALY_ID AND l.STATUS = 'PENDING_APPROVAL'
        WHERE a.STATUS = 'ACKNOWLEDGED'
          AND a.SEVERITY IN ('HIGH', 'CRITICAL')
          AND NOT EXISTS (
              SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.APPROVAL_TOKENS t
              WHERE t.ANOMALY_ID = a.ANOMALY_ID
                AND t.USED = FALSE
                AND t.EXPIRES_AT > CURRENT_TIMESTAMP())))
THEN CALL FINOPS_GUARDIAN.PUBLIC.SEND_PENDING_APPROVAL_EMAILS();

-- ============================================================================
-- 15. SEED THE DEMO
-- ============================================================================

TRUNCATE TABLE USAGE_ANOMALIES;
TRUNCATE TABLE AUDIT_LOG;
TRUNCATE TABLE NOTIFICATIONS;
TRUNCATE TABLE AGENT_EXECUTION_LOG;
TRUNCATE TABLE APPROVAL_TOKENS;
TRUNCATE TABLE SAVINGS_HISTORY;

CALL DETECT_IDLE_COMPUTE_DEMO();
CALL DETECT_COST_SPIKE_DEMO(2.5);
CALL DETECT_OVERSIZED_WAREHOUSE(0.40);
CALL DETECT_LONG_RUNNING_QUERIES(600);
CALL APPLY_FIXES();
CALL SNAPSHOT_SAVINGS();

-- Backfill six prior days so the savings trend chart has a shape on day one.
INSERT INTO SAVINGS_HISTORY (SNAPSHOT_DATE, ANOMALIES_DETECTED, CREDITS_WASTED, CREDITS_SAVED, DOLLAR_SAVED)
SELECT
    DATEADD('day', -D, CURRENT_DATE()),
    ROUND(today.N * (7 - D) / 7.0, 0),
    ROUND(today.W * (7 - D) / 7.0, 4),
    ROUND(today.S * (7 - D) / 7.0, 4),
    ROUND(today.S * (7 - D) / 7.0 * 3.00, 2)
FROM (SELECT 1 AS D UNION ALL SELECT 2 UNION ALL SELECT 3
      UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6) days
CROSS JOIN (
    SELECT COUNT(*) AS N,
           COALESCE(SUM(CREDITS_WASTED), 0) AS W,
           COALESCE(SUM(CASE WHEN STATUS = 'RESOLVED' THEN CREDITS_WASTED ELSE 0 END), 0) AS S
    FROM USAGE_ANOMALIES
) today
WHERE NOT EXISTS (
    SELECT 1 FROM SAVINGS_HISTORY h WHERE h.SNAPSHOT_DATE = DATEADD('day', -days.D, CURRENT_DATE()));

-- ============================================================================
-- 16. TURN ON SCHEDULED MONITORING (optional - run when you want it live)
-- ============================================================================
-- ALTER TASK TASK_SNAPSHOT_SAVINGS    RESUME;
-- ALTER TASK TASK_EVALUATE_ALERTS     RESUME;
-- ALTER TASK TASK_APPLY_FIXES         RESUME;
-- ALTER TASK TASK_DETECT_LONG_QUERIES RESUME;
-- ALTER TASK TASK_DETECT_OVERSIZED    RESUME;
-- ALTER TASK TASK_DETECT_SPIKE        RESUME;
-- ALTER TASK TASK_DETECT_IDLE         RESUME;   -- root task last
-- ALTER ALERT HIGH_SEVERITY_ALERT     RESUME;
--
-- Email delivery and real remediation are both opt-in:
--   UPDATE AGENT_CONFIG SET CONFIG_VALUE = 'you@example.com' WHERE CONFIG_KEY = 'ALERT_RECIPIENT';
--   UPDATE AGENT_CONFIG SET CONFIG_VALUE = 'FALSE'           WHERE CONFIG_KEY = 'DRY_RUN';
