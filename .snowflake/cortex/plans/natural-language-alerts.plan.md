# Plan: Natural Language Alerts

## Overview

Add a "Smart Alerts" section to the Intelligence tab where users can create monitoring alerts using natural language. Cortex AI parses the intent into a structured alert configuration (threshold, warehouse, metric, frequency). Active alerts are displayed with their status.

## Implementation

### 1. Create SMART_ALERTS table in Snowflake

```sql
CREATE TABLE IF NOT EXISTS FINOPS_GUARDIAN.PUBLIC.SMART_ALERTS (
    ALERT_ID NUMBER AUTOINCREMENT,
    NATURAL_LANGUAGE_RULE VARCHAR(500),
    PARSED_METRIC VARCHAR(100),       -- e.g. 'daily_spend', 'credits_per_hour', 'idle_minutes'
    PARSED_THRESHOLD FLOAT,           -- e.g. 50.00
    PARSED_WAREHOUSE VARCHAR(200),    -- e.g. 'ANY' or specific warehouse
    PARSED_CONDITION VARCHAR(50),     -- 'greater_than', 'less_than', 'equals'
    IS_ACTIVE BOOLEAN DEFAULT TRUE,
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    LAST_TRIGGERED_AT TIMESTAMP,
    TRIGGER_COUNT NUMBER DEFAULT 0
);
```

### 2. Add "Smart Alerts" section to Intelligence tab

After the AI Chat section, add:
- **"🔔 Smart Alerts — Natural Language"** header
- Text input: "Describe your alert rule in plain English..."
- On submit → call Cortex AI to parse into structured fields
- Show parsed result in a confirmation card (metric, threshold, warehouse, condition)
- "Activate Alert" button to insert into SMART_ALERTS table

### 3. Cortex AI parsing prompt

Send the user's text to `SNOWFLAKE.CORTEX.COMPLETE` with a structured prompt that returns JSON:
```
Parse this alert rule into JSON: {"metric": "...", "threshold": ..., "warehouse": "...", "condition": "..."}
Valid metrics: daily_spend, weekly_spend, credits_per_hour, idle_minutes, query_count
Valid conditions: greater_than, less_than, equals
If no warehouse specified, use "ANY"
```

### 4. Display active alerts

Below the input, show a table/card list of active alerts from SMART_ALERTS:
- Natural language rule text
- Parsed badge (e.g., "💰 daily_spend > $50 on ANY")
- Status indicator (Active 🟢 / Triggered 🔴)
- Trigger count
- Delete button to deactivate

### 5. UI Design

Cards matching the existing design system:
- White background, border-radius 12px, subtle border
- Green "Active" badge or red "Triggered" badge
- Parsed rule shown as inline tags

## Constraints
- No `snowflake.cortex` Python import — use SQL-based `SNOWFLAKE.CORTEX.COMPLETE()`
- SiS ~1.22 limitations apply
- JSON parsing from Cortex response handled with `json.loads()` in Python
