# Plan: Match Reference Sidebar & UI

## Overview

Update the sidebar layout and main content header to match the polished reference screenshot. The reference shows a cleaner, more professional sidebar with distinct sections and a refined main header without the "Active" pill badge.

## Changes Required

### 1. Sidebar Header
**Current**: "FinOps Guardian" + "AI-powered cost intelligence"  
**Target**: "FinOps Guardian" + "Expense Intelligence ✨"

### 2. Quick Stats Section  
**Current**: "Open Issues" (count) + "Unread" (🔔 count)  
**Target**: "QUICK STATS" header + two cards with icons:
- 🖥 `{servers}` + "Servers" label (use warehouse count)  
- 👥 `{users}` + "Users" label (use notification unread count for now)

### 3. Navigation Labels
**Current**: Emoji-prefixed labels like "📊 Executive Summary"  
**Target**: Clean labels with small colored dot indicators:
- 📊 Executive Summary (blue dot active)
- ⚙️ Operations  
- ✅ Approvals  
- 🧠 Intelligence  
- 📋 Compliance  
- 🔔 Notifications (10)  
- 📜 Audit Trail  

Keep existing emojis but ensure the active state styling (indigo left border + bold text) is prominent.

### 4. Quick Actions Section (replaces Agent Controls)
**Current**: "AGENT CONTROLS" + "Run AI scans and auto-remediation" + Idle Scan / Spike Scan + Apply Fixes + Reset Demo  
**Target**:
- "QUICK ACTIONS" section header
- "Shortcuts for common tasks" caption
- Two buttons: "📤 Upload Scan" + "📋 Explorer"
- Green full-width "+ New Scan" button (primary)
- "Scan Profile" dropdown (selectbox)
- Keep Reset Demo expander below

### 5. Page Header
**Current**: Title + "● Active" pill + date range pill  
**Target**: Title + subtitle "Monitor your app health, usage and key metrics at a glance" + date range (dropdown style with ▾)

### 6. Footer
**Current**: "v0.5 · Snowflake Cortex AI" + "Hackathon 2026"  
**Target**: "© 2025 FinOps Guardian" + "All rights reserved"

## Constraints
- SiS ~1.22, no modern Streamlit features
- Keep all existing tab logic and functionality intact
- Only changing sidebar structure and page header presentation
