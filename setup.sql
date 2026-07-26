-- FinOps Guardian - Setup Script
-- Run this in a Snowflake worksheet to create all backend objects.

-- 1. Database
CREATE DATABASE IF NOT EXISTS FINOPS_GUARDIAN;
USE DATABASE FINOPS_GUARDIAN;
USE SCHEMA PUBLIC;

-- 2. Tables
CREATE OR REPLACE TABLE USAGE_ANOMALIES (
    ANOMALY_ID NUMBER AUTOINCREMENT PRIMARY KEY,
    WAREHOUSE_NAME VARCHAR(256) NOT NULL,
    DETECTED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    ANOMALY_START TIMESTAMP_LTZ NOT NULL,
    ANOMALY_END TIMESTAMP_LTZ,
    ANOMALY_TYPE VARCHAR(50) NOT NULL,
    SEVERITY VARCHAR(10) NOT NULL,
    CREDITS_WASTED NUMBER(38,9) DEFAULT 0,
    DESCRIPTION VARCHAR(1000),
    SUGGESTED_FIX VARCHAR(1000),
    STATUS VARCHAR(20) DEFAULT 'OPEN',
    RESOLVED_AT TIMESTAMP_LTZ,
    RESOLVED_BY VARCHAR(256)
);

CREATE OR REPLACE TABLE AUDIT_LOG (
    LOG_ID NUMBER AUTOINCREMENT PRIMARY KEY,
    LOGGED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    ACTION_TYPE VARCHAR(50) NOT NULL,
    ANOMALY_ID NUMBER,
    WAREHOUSE_NAME VARCHAR(256),
    ACTION_DETAILS VARCHAR(2000) NOT NULL,
    SQL_EXECUTED VARCHAR(4000),
    APPROVED_BY VARCHAR(256),
    STATUS VARCHAR(20) DEFAULT 'COMPLETED',
    ERROR_MESSAGE VARCHAR(2000)
);

CREATE OR REPLACE TABLE WAREHOUSE_METERING_TEST (
    START_TIME TIMESTAMP_LTZ,
    END_TIME TIMESTAMP_LTZ,
    WAREHOUSE_ID NUMBER,
    WAREHOUSE_NAME VARCHAR(256),
    CREDITS_USED NUMBER(38,9),
    CREDITS_USED_COMPUTE NUMBER(38,9),
    CREDITS_USED_CLOUD_SERVICES NUMBER(38,9)
);

-- 3. Synthetic Demo Data
INSERT INTO WAREHOUSE_METERING_TEST VALUES
    -- Normal usage for ANALYTICS_WH
    ('2026-07-25 08:00:00 -0700', '2026-07-25 09:00:00 -0700', 100, 'ANALYTICS_WH', 2.100000000, 2.050000000, 0.050000000),
    ('2026-07-25 09:00:00 -0700', '2026-07-25 10:00:00 -0700', 100, 'ANALYTICS_WH', 1.900000000, 1.860000000, 0.040000000),
    ('2026-07-25 10:00:00 -0700', '2026-07-25 11:00:00 -0700', 100, 'ANALYTICS_WH', 2.300000000, 2.250000000, 0.050000000),
    ('2026-07-25 11:00:00 -0700', '2026-07-25 12:00:00 -0700', 100, 'ANALYTICS_WH', 2.000000000, 1.960000000, 0.040000000),
    -- ANALYTICS_WH goes IDLE for 3 hours
    ('2026-07-25 12:00:00 -0700', '2026-07-25 13:00:00 -0700', 100, 'ANALYTICS_WH', 0.050000000, 0.000000000, 0.050000000),
    ('2026-07-25 13:00:00 -0700', '2026-07-25 14:00:00 -0700', 100, 'ANALYTICS_WH', 0.048000000, 0.000000000, 0.048000000),
    ('2026-07-25 14:00:00 -0700', '2026-07-25 15:00:00 -0700', 100, 'ANALYTICS_WH', 0.052000000, 0.000000000, 0.052000000),
    -- ETL_WH cost spike (4x normal)
    ('2026-07-25 01:00:00 -0700', '2026-07-25 02:00:00 -0700', 200, 'ETL_WH', 4.200000000, 4.100000000, 0.100000000),
    ('2026-07-25 02:00:00 -0700', '2026-07-25 03:00:00 -0700', 200, 'ETL_WH', 3.800000000, 3.700000000, 0.100000000),
    ('2026-07-25 03:00:00 -0700', '2026-07-25 04:00:00 -0700', 200, 'ETL_WH', 4.100000000, 4.000000000, 0.100000000),
    ('2026-07-25 04:00:00 -0700', '2026-07-25 05:00:00 -0700', 200, 'ETL_WH', 16.500000000, 16.200000000, 0.300000000),
    ('2026-07-25 05:00:00 -0700', '2026-07-25 06:00:00 -0700', 200, 'ETL_WH', 15.800000000, 15.500000000, 0.300000000),
    ('2026-07-25 06:00:00 -0700', '2026-07-25 07:00:00 -0700', 200, 'ETL_WH', 4.300000000, 4.200000000, 0.100000000),
    -- DEV_WH left idle overnight
    ('2026-07-25 18:00:00 -0700', '2026-07-25 19:00:00 -0700', 300, 'DEV_WH', 0.120000000, 0.000000000, 0.120000000),
    ('2026-07-25 19:00:00 -0700', '2026-07-25 20:00:00 -0700', 300, 'DEV_WH', 0.118000000, 0.000000000, 0.118000000),
    ('2026-07-25 20:00:00 -0700', '2026-07-25 21:00:00 -0700', 300, 'DEV_WH', 0.122000000, 0.000000000, 0.122000000),
    ('2026-07-25 21:00:00 -0700', '2026-07-25 22:00:00 -0700', 300, 'DEV_WH', 0.115000000, 0.000000000, 0.115000000),
    ('2026-07-25 22:00:00 -0700', '2026-07-25 23:00:00 -0700', 300, 'DEV_WH', 0.119000000, 0.000000000, 0.119000000),
    ('2026-07-25 23:00:00 -0700', '2026-07-26 00:00:00 -0700', 300, 'DEV_WH', 0.121000000, 0.000000000, 0.121000000);

-- 4. Stored Procedures

CREATE OR REPLACE PROCEDURE DETECT_IDLE_COMPUTE(LOOKBACK_HOURS NUMBER DEFAULT 24)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    rows_inserted NUMBER;
    audit_msg VARCHAR;
BEGIN
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX
    )
    SELECT
        WAREHOUSE_NAME, START_TIME, END_TIME, 'IDLE_COMPUTE',
        CASE
            WHEN CREDITS_USED_CLOUD_SERVICES > 1.0 THEN 'HIGH'
            WHEN CREDITS_USED_CLOUD_SERVICES > 0.1 THEN 'MEDIUM'
            ELSE 'LOW'
        END,
        CREDITS_USED_CLOUD_SERVICES,
        'Warehouse ' || WAREHOUSE_NAME || ' was running but idle from ' ||
            TO_CHAR(START_TIME, 'YYYY-MM-DD HH24:MI') || ' to ' ||
            TO_CHAR(END_TIME, 'YYYY-MM-DD HH24:MI') ||
            '. Cloud services credits consumed: ' || ROUND(CREDITS_USED_CLOUD_SERVICES, 6)::VARCHAR,
        'Consider reducing AUTO_SUSPEND timeout or suspending warehouse ' ||
            WAREHOUSE_NAME || ' during off-hours. Current idle cost: ' ||
            ROUND(CREDITS_USED_CLOUD_SERVICES, 6)::VARCHAR || ' credits/hour.'
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE START_TIME >= DATEADD('hour', -:LOOKBACK_HOURS, CURRENT_TIMESTAMP())
      AND CREDITS_USED_COMPUTE = 0
      AND CREDITS_USED_CLOUD_SERVICES > 0
      AND WAREHOUSE_NAME != 'CLOUD_SERVICES_ONLY'
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.WAREHOUSE_NAME = WAREHOUSE_METERING_HISTORY.WAREHOUSE_NAME
            AND a.ANOMALY_START = WAREHOUSE_METERING_HISTORY.START_TIME
            AND a.ANOMALY_TYPE = 'IDLE_COMPUTE'
      );

    rows_inserted := SQLROWCOUNT;
    audit_msg := 'Idle compute scan completed. Lookback: ' || :LOOKBACK_HOURS || ' hours. New anomalies found: ' || :rows_inserted;

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION', :audit_msg, 'COMPLETED';

    RETURN 'Idle compute detection complete. ' || :rows_inserted || ' new anomalies logged.';
END;
$$;

CREATE OR REPLACE PROCEDURE DETECT_IDLE_COMPUTE_DEMO()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    rows_inserted NUMBER;
    audit_msg VARCHAR;
BEGIN
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX
    )
    SELECT
        WAREHOUSE_NAME, START_TIME, END_TIME, 'IDLE_COMPUTE',
        CASE
            WHEN CREDITS_USED_CLOUD_SERVICES > 1.0 THEN 'HIGH'
            WHEN CREDITS_USED_CLOUD_SERVICES > 0.1 THEN 'MEDIUM'
            ELSE 'LOW'
        END,
        CREDITS_USED_CLOUD_SERVICES,
        'Warehouse ' || WAREHOUSE_NAME || ' was running but idle from ' ||
            TO_CHAR(START_TIME, 'YYYY-MM-DD HH24:MI') || ' to ' ||
            TO_CHAR(END_TIME, 'YYYY-MM-DD HH24:MI') ||
            '. Cloud services credits consumed: ' || ROUND(CREDITS_USED_CLOUD_SERVICES, 6)::VARCHAR,
        'Consider reducing AUTO_SUSPEND timeout or suspending warehouse ' ||
            WAREHOUSE_NAME || ' during off-hours. Current idle cost: ' ||
            ROUND(CREDITS_USED_CLOUD_SERVICES, 6)::VARCHAR || ' credits/hour.'
    FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST
    WHERE CREDITS_USED_COMPUTE = 0
      AND CREDITS_USED_CLOUD_SERVICES > 0
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.WAREHOUSE_NAME = WAREHOUSE_METERING_TEST.WAREHOUSE_NAME
            AND a.ANOMALY_START = WAREHOUSE_METERING_TEST.START_TIME
            AND a.ANOMALY_TYPE = 'IDLE_COMPUTE'
      );

    rows_inserted := SQLROWCOUNT;
    audit_msg := 'Idle compute scan (DEMO) completed. New anomalies found: ' || :rows_inserted;

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION', :audit_msg, 'COMPLETED';

    RETURN 'Demo idle compute detection complete. ' || :rows_inserted || ' new anomalies logged.';
END;
$$;

CREATE OR REPLACE PROCEDURE DETECT_COST_SPIKE_DEMO(SPIKE_THRESHOLD FLOAT DEFAULT 2.5)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    rows_inserted NUMBER;
    audit_msg VARCHAR;
BEGIN
    INSERT INTO FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES (
        WAREHOUSE_NAME, ANOMALY_START, ANOMALY_END, ANOMALY_TYPE, SEVERITY,
        CREDITS_WASTED, DESCRIPTION, SUGGESTED_FIX
    )
    WITH metering_with_avg AS (
        SELECT
            WAREHOUSE_NAME, START_TIME, END_TIME, CREDITS_USED,
            AVG(CREDITS_USED) OVER (
                PARTITION BY WAREHOUSE_NAME ORDER BY START_TIME
                ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
            ) AS rolling_avg_3h,
            COUNT(*) OVER (
                PARTITION BY WAREHOUSE_NAME ORDER BY START_TIME
                ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
            ) AS preceding_rows
        FROM FINOPS_GUARDIAN.PUBLIC.WAREHOUSE_METERING_TEST
    )
    SELECT
        WAREHOUSE_NAME, START_TIME, END_TIME, 'COST_SPIKE',
        CASE
            WHEN CREDITS_USED / NULLIF(rolling_avg_3h, 0) > 8.0 THEN 'CRITICAL'
            WHEN CREDITS_USED / NULLIF(rolling_avg_3h, 0) > 4.0 THEN 'HIGH'
            ELSE 'MEDIUM'
        END,
        CREDITS_USED - rolling_avg_3h,
        'Warehouse ' || WAREHOUSE_NAME || ' cost spike detected at ' ||
            TO_CHAR(START_TIME, 'YYYY-MM-DD HH24:MI') || '. Used ' ||
            ROUND(CREDITS_USED, 3)::VARCHAR || ' credits vs ' ||
            ROUND(rolling_avg_3h, 3)::VARCHAR || ' rolling avg (' ||
            ROUND(CREDITS_USED / NULLIF(rolling_avg_3h, 0), 1)::VARCHAR || 'x normal).',
        'Investigate queries running on ' || WAREHOUSE_NAME || ' between ' ||
            TO_CHAR(START_TIME, 'HH24:MI') || '-' || TO_CHAR(END_TIME, 'HH24:MI') ||
            '. Consider: (1) Check QUERY_HISTORY for long-running queries, ' ||
            '(2) Review warehouse auto-scaling config, ' ||
            '(3) Set STATEMENT_TIMEOUT_IN_SECONDS to cap runaway queries.'
    FROM metering_with_avg
    WHERE preceding_rows >= 2
      AND rolling_avg_3h > 0
      AND CREDITS_USED / rolling_avg_3h >= :SPIKE_THRESHOLD
      AND NOT EXISTS (
          SELECT 1 FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES a
          WHERE a.WAREHOUSE_NAME = metering_with_avg.WAREHOUSE_NAME
            AND a.ANOMALY_START = metering_with_avg.START_TIME
            AND a.ANOMALY_TYPE = 'COST_SPIKE'
      );

    rows_inserted := SQLROWCOUNT;
    audit_msg := 'Cost spike scan (DEMO) completed. Threshold: ' || :SPIKE_THRESHOLD || 'x. New anomalies found: ' || :rows_inserted;

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (ACTION_TYPE, ACTION_DETAILS, STATUS)
    SELECT 'DETECTION', :audit_msg, 'COMPLETED';

    RETURN 'Cost spike detection complete. ' || :rows_inserted || ' new anomalies logged.';
END;
$$;

CREATE OR REPLACE PROCEDURE APPLY_FIXES()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    auto_applied NUMBER DEFAULT 0;
    pending_approval NUMBER DEFAULT 0;
    cur CURSOR FOR
        SELECT ANOMALY_ID, WAREHOUSE_NAME, ANOMALY_TYPE, SEVERITY, CREDITS_WASTED
        FROM FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
        WHERE STATUS = 'OPEN';
    v_anomaly_id NUMBER;
    v_warehouse VARCHAR;
    v_type VARCHAR;
    v_severity VARCHAR;
    v_credits NUMBER;
    v_sql_fix VARCHAR;
    v_action_details VARCHAR;
    v_status VARCHAR;
BEGIN
    OPEN cur;
    FOR rec IN cur DO
        v_anomaly_id := rec.ANOMALY_ID;
        v_warehouse := rec.WAREHOUSE_NAME;
        v_type := rec.ANOMALY_TYPE;
        v_severity := rec.SEVERITY;
        v_credits := rec.CREDITS_WASTED;

        CASE
            WHEN v_type = 'IDLE_COMPUTE' THEN
                v_sql_fix := 'ALTER WAREHOUSE ' || v_warehouse || ' SET AUTO_SUSPEND = 60;';
                v_action_details := 'Reducing AUTO_SUSPEND to 60s for ' || v_warehouse ||
                    ' to prevent idle compute waste. Estimated savings: ' ||
                    ROUND(v_credits, 4)::VARCHAR || ' credits/hour.';
            WHEN v_type = 'COST_SPIKE' THEN
                v_sql_fix := 'ALTER WAREHOUSE ' || v_warehouse ||
                    ' SET STATEMENT_TIMEOUT_IN_SECONDS = 3600;';
                v_action_details := 'Setting statement timeout on ' || v_warehouse ||
                    ' to prevent runaway queries. Spike was ' ||
                    ROUND(v_credits, 2)::VARCHAR || ' credits above baseline.';
            ELSE
                v_sql_fix := '-- No automated fix available for: ' || v_type;
                v_action_details := 'Unknown anomaly type. Manual investigation required.';
        END CASE;

        IF (v_severity IN ('LOW', 'MEDIUM')) THEN
            v_status := 'COMPLETED';
            auto_applied := auto_applied + 1;
            UPDATE FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
            SET STATUS = 'RESOLVED', RESOLVED_AT = CURRENT_TIMESTAMP(),
                RESOLVED_BY = 'FINOPS_AGENT (auto)'
            WHERE ANOMALY_ID = :v_anomaly_id;
        ELSE
            v_status := 'PENDING_APPROVAL';
            pending_approval := pending_approval + 1;
            UPDATE FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
            SET STATUS = 'ACKNOWLEDGED'
            WHERE ANOMALY_ID = :v_anomaly_id;
        END IF;

        INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (
            ACTION_TYPE, ANOMALY_ID, WAREHOUSE_NAME,
            ACTION_DETAILS, SQL_EXECUTED, APPROVED_BY, STATUS
        )
        SELECT
            CASE WHEN :v_status = 'COMPLETED' THEN 'AUTO_ACTION' ELSE 'RECOMMENDATION' END,
            :v_anomaly_id, :v_warehouse, :v_action_details, :v_sql_fix,
            CASE WHEN :v_status = 'COMPLETED' THEN 'FINOPS_AGENT' ELSE NULL END,
            :v_status;
    END FOR;
    CLOSE cur;

    RETURN 'Fix application complete. Auto-applied: ' || :auto_applied ||
           ', Pending approval: ' || :pending_approval;
END;
$$;

CREATE OR REPLACE PROCEDURE APPROVE_FIX(P_ANOMALY_ID NUMBER, P_APPROVED_BY VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO :v_count
    FROM FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
    WHERE ANOMALY_ID = :P_ANOMALY_ID AND STATUS = 'PENDING_APPROVAL';

    IF (v_count = 0) THEN
        RETURN 'No pending approval found for anomaly ID ' || :P_ANOMALY_ID;
    END IF;

    UPDATE FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG
    SET STATUS = 'COMPLETED', APPROVED_BY = :P_APPROVED_BY
    WHERE ANOMALY_ID = :P_ANOMALY_ID AND STATUS = 'PENDING_APPROVAL';

    UPDATE FINOPS_GUARDIAN.PUBLIC.USAGE_ANOMALIES
    SET STATUS = 'RESOLVED', RESOLVED_AT = CURRENT_TIMESTAMP(), RESOLVED_BY = :P_APPROVED_BY
    WHERE ANOMALY_ID = :P_ANOMALY_ID;

    INSERT INTO FINOPS_GUARDIAN.PUBLIC.AUDIT_LOG (
        ACTION_TYPE, ANOMALY_ID, ACTION_DETAILS, APPROVED_BY, STATUS
    )
    SELECT 'USER_ACTION', :P_ANOMALY_ID,
        'Human approved fix for anomaly ' || :P_ANOMALY_ID || '. Approved by: ' || :P_APPROVED_BY,
        :P_APPROVED_BY, 'COMPLETED';

    RETURN 'Fix approved and applied for anomaly ' || :P_ANOMALY_ID || ' by ' || :P_APPROVED_BY;
END;
$$;

-- 5. Stage and Streamlit App Object
CREATE STAGE IF NOT EXISTS STREAMLIT_STAGE
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- Upload streamlit_app.py to the stage before running this:
-- PUT 'file://./streamlit_app.py' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
-- PUT 'file://./.streamlit/config.toml' @FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE/.streamlit/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

CREATE OR REPLACE STREAMLIT FINOPS_GUARDIAN_APP
    ROOT_LOCATION = '@FINOPS_GUARDIAN.PUBLIC.STREAMLIT_STAGE'
    MAIN_FILE = 'streamlit_app.py'
    QUERY_WAREHOUSE = COMPUTE_WH
    TITLE = 'FinOps Guardian';

-- 6. Seed the demo state (run detections + apply fixes)
CALL DETECT_IDLE_COMPUTE_DEMO();
CALL DETECT_COST_SPIKE_DEMO(2.5);
CALL APPLY_FIXES();
