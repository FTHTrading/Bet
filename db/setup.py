"""
Database setup — creates SQLite schema for bet tracking.
Run once: python db/setup.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "kalishi_edge.db"


def create_schema():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS bets (
        id              TEXT PRIMARY KEY,
        sport           TEXT NOT NULL,
        event           TEXT NOT NULL,
        market          TEXT NOT NULL,
        pick            TEXT NOT NULL,
        american_odds   INTEGER NOT NULL,
        decimal_odds    REAL NOT NULL,
        stake           REAL NOT NULL,
        ev_pct          REAL DEFAULT 0,
        edge_pct        REAL DEFAULT 0,
        strategy        TEXT DEFAULT 'kelly',
        result          TEXT,           -- 'win', 'loss', 'push', NULL=open
        pnl             REAL,
        closing_odds    INTEGER,
        clv             REAL,
        placed_at       TEXT NOT NULL,
        settled_at      TEXT,
        notes           TEXT
    );

    CREATE TABLE IF NOT EXISTS bankroll_snapshots (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date   TEXT NOT NULL,
        bankroll        REAL NOT NULL,
        daily_pnl       REAL DEFAULT 0,
        roi_pct         REAL DEFAULT 0,
        win_rate        REAL DEFAULT 0,
        total_bets      INTEGER DEFAULT 0,
        open_bets       INTEGER DEFAULT 0,
        clv_avg         REAL DEFAULT 0,
        created_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS arb_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event           TEXT NOT NULL,
        sport           TEXT,
        arb_type        TEXT,
        profit_pct      REAL,
        total_stake     REAL,
        leg_a_book      TEXT,
        leg_a_side      TEXT,
        leg_a_odds      REAL,
        leg_b_book      TEXT,
        leg_b_side      TEXT,
        leg_b_odds      REAL,
        guaranteed_profit REAL,
        scan_time       TEXT
    );

    CREATE TABLE IF NOT EXISTS line_movements (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        sport           TEXT,
        event           TEXT,
        book            TEXT,
        market          TEXT,
        side            TEXT,
        prev_decimal    REAL,
        curr_decimal    REAL,
        movement        REAL,
        significance    TEXT,
        ts              TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_bets_sport ON bets(sport);
    CREATE INDEX IF NOT EXISTS idx_bets_result ON bets(result);
    CREATE INDEX IF NOT EXISTS idx_bets_placed_at ON bets(placed_at);
    CREATE INDEX IF NOT EXISTS idx_snapshots_date ON bankroll_snapshots(snapshot_date);

    CREATE TABLE IF NOT EXISTS ai_analysis (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event           TEXT NOT NULL,
        sport           TEXT,
        market          TEXT,
        pick            TEXT,
        conviction      TEXT,
        grade           TEXT,
        action          TEXT,
        edge_pct        REAL DEFAULT 0,
        ev_pct          REAL DEFAULT 0,
        one_line_thesis TEXT,
        full_reasoning  TEXT,
        risk_factors    TEXT,
        model_version   TEXT DEFAULT 'gpt-4o',
        created_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS agent_decisions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_name      TEXT NOT NULL,
        decision_type   TEXT NOT NULL,
        input_json      TEXT,
        output_json     TEXT,
        confidence      REAL DEFAULT 0,
        latency_ms      INTEGER DEFAULT 0,
        created_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS steam_alerts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event           TEXT NOT NULL,
        sport           TEXT,
        market          TEXT,
        alert_type      TEXT,
        conviction      TEXT,
        move_direction  TEXT,
        move_amount     REAL,
        public_pct      REAL,
        book            TEXT,
        alert_json      TEXT,
        detected_at     TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS daily_briefings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        date            TEXT UNIQUE,
        briefing_json   TEXT,
        created_at      TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_ai_analysis_event ON ai_analysis(event);
    CREATE INDEX IF NOT EXISTS idx_ai_analysis_grade ON ai_analysis(grade);
    CREATE INDEX IF NOT EXISTS idx_steam_event ON steam_alerts(event);
    CREATE INDEX IF NOT EXISTS idx_steam_conviction ON steam_alerts(conviction);
    CREATE INDEX IF NOT EXISTS idx_agent_decisions_name ON agent_decisions(agent_name);
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Schema created at {DB_PATH}")


if __name__ == "__main__":
    create_schema()
