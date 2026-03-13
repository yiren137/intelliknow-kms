import sqlite3
from contextlib import contextmanager
from config.settings import get_settings

settings = get_settings()


def get_db_path() -> str:
    return settings.db_path


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn):
    """Add new columns to existing tables without dropping data."""
    # intent_spaces: keywords, confidence_threshold
    existing = {row[1] for row in conn.execute("PRAGMA table_info(intent_spaces)")}
    if "keywords" not in existing:
        conn.execute("ALTER TABLE intent_spaces ADD COLUMN keywords TEXT DEFAULT ''")
    if "confidence_threshold" not in existing:
        conn.execute("ALTER TABLE intent_spaces ADD COLUMN confidence_threshold REAL DEFAULT 0.7")

    # documents: file_size_bytes
    existing = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    if "file_size_bytes" not in existing:
        conn.execute("ALTER TABLE documents ADD COLUMN file_size_bytes INTEGER DEFAULT 0")

    # query_logs: feedback (1=thumbs up, -1=thumbs down, NULL=no feedback)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(query_logs)")}
    if "feedback" not in existing:
        conn.execute("ALTER TABLE query_logs ADD COLUMN feedback INTEGER")
    if "cache_hit" not in existing:
        conn.execute("ALTER TABLE query_logs ADD COLUMN cache_hit INTEGER NOT NULL DEFAULT 0")

    # With temperature=10 softmax scaling, clear routing decisions score 0.4–0.9+.
    # 0.30 rejects genuinely ambiguous queries while remaining reachable for
    # moderately confident classifications (borderline queries score ~0.30–0.40).
    conn.execute(
        """UPDATE intent_spaces SET confidence_threshold = 0.30
           WHERE name IN ('hr', 'legal', 'finance', 'general')"""
    )

    # Enrich intent-space descriptions/keywords so the embedding classifier can
    # distinguish closely-related queries (e.g. finance-travel vs general-travel).
    keyword_updates = {
        "hr": (
            "HR policies, employee handbook, onboarding, offboarding, employee benefits, "
            "health benefits, health insurance, medical dental vision coverage, "
            "leave, vacation, sick days, parental leave, "
            "performance review process, annual performance review, review cycle, "
            "performance appraisal, employee evaluation, goal setting, performance assessment, "
            "severance, remote work, employee guidelines",
            "vacation leave sick parental onboarding offboarding benefits health benefits "
            "health insurance medical dental vision coverage performance review "
            "performance review process annual review review cycle "
            "performance appraisal employee evaluation goal setting performance assessment "
            "severance remote work PTO termination employee",
        ),
        "legal": (
            "Legal documents, contracts, compliance, NDA, non-disclosure, "
            "intellectual property, GDPR, data privacy, anti-bribery, regulatory, "
            "submit contract, contract submission, legal review, contract approval",
            "NDA contract compliance GDPR intellectual property bribery regulatory "
            "legal privacy data protection submit contract contract submission "
            "legal review contract approval sign agreement",
        ),
        "finance": (
            "Financial policies, expense reimbursement, annual corporate budget, "
            "budget approval, travel expenses, corporate credit card, per diem, "
            "meal allowance, procurement, invoice, accounts payable, spending limit, "
            "financial reports, cost centre, "
            "book business travel, travel booking, book flights, business trip",
            "expense reimbursement annual corporate budget travel credit card per diem "
            "meal allowance procurement invoice accounts payable financial approval "
            "spending limit reimbursed book business travel travel booking "
            "book flights business trip concur",
        ),
        "general": (
            "General company knowledge, company values, culture, announcements, "
            "miscellaneous policies, tools, all-hands, learning and development L&D, "
            "headquarters, company handbook",
            "company values culture announcements tools all-hands learning development "
            "L&D budget handbook general policies headquarters",
        ),
    }
    for name, (desc, kw) in keyword_updates.items():
        conn.execute(
            "UPDATE intent_spaces SET description = ?, keywords = ? WHERE name = ?",
            (desc, kw, name),
        )


def init_db():
    with get_db_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS intent_spaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                keywords TEXT DEFAULT '',
                confidence_threshold REAL DEFAULT 0.7,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                intent_space_id INTEGER NOT NULL,
                file_type TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                indexed_at TEXT,
                FOREIGN KEY (intent_space_id) REFERENCES intent_spaces(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                faiss_id INTEGER NOT NULL,
                intent_space_id INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                page_number INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS query_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'api',
                user_id TEXT,
                intent_space_id INTEGER,
                intent_space_name TEXT,
                confidence_score REAL,
                response_status TEXT NOT NULL DEFAULT 'success',
                response_text TEXT,
                latency_ms INTEGER,
                documents_accessed TEXT DEFAULT '[]',
                cache_hit INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (intent_space_id) REFERENCES intent_spaces(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS document_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                query_log_id INTEGER NOT NULL,
                accessed_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (query_log_id) REFERENCES query_logs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS bot_integrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 0,
                config_json TEXT DEFAULT '{}',
                last_seen_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

        _migrate(conn)

        # Seed intent spaces
        # confidence_threshold of 0.30 suits the temperature-scaled (T=10) softmax classifier:
        # clear routing decisions score 0.4–0.9+; 0.30 rejects genuinely ambiguous queries.
        seeds = [
            (
                "hr", "Human Resources",
                "HR policies, employee handbook, onboarding, offboarding, employee benefits, "
                "health benefits, health insurance, medical dental vision coverage, "
                "leave, vacation, sick days, parental leave, "
                "performance review process, annual performance review, review cycle, "
                "performance appraisal, employee evaluation, goal setting, performance assessment, "
                "severance, remote work, employee guidelines",
                "vacation leave sick parental onboarding offboarding benefits health benefits "
                "health insurance medical dental vision coverage performance review "
                "performance review process annual review review cycle "
                "performance appraisal employee evaluation goal setting performance assessment "
                "severance remote work PTO termination employee",
            ),
            (
                "legal", "Legal",
                "Legal documents, contracts, compliance, NDA, non-disclosure, "
                "intellectual property, GDPR, data privacy, anti-bribery, regulatory, "
                "submit contract, contract submission, legal review, contract approval",
                "NDA contract compliance GDPR intellectual property bribery regulatory "
                "legal privacy data protection submit contract contract submission "
                "legal review contract approval sign agreement",
            ),
            (
                "finance", "Finance",
                "Financial policies, expense reimbursement, annual corporate budget, "
                "budget approval, travel expenses, corporate credit card, per diem, "
                "meal allowance, procurement, invoice, accounts payable, spending limit, "
                "financial reports, cost centre, "
                "book business travel, travel booking, book flights, business trip",
                "expense reimbursement annual corporate budget travel credit card per diem "
                "meal allowance procurement invoice accounts payable financial approval "
                "spending limit reimbursed book business travel travel booking "
                "book flights business trip concur",
            ),
            (
                "general", "General",
                "General company knowledge, company values, culture, announcements, "
                "miscellaneous policies, tools, all-hands, learning and development L&D, "
                "headquarters, company handbook",
                "company values culture announcements tools all-hands learning development "
                "L&D budget handbook general policies headquarters",
            ),
        ]
        for name, display_name, description, keywords in seeds:
            conn.execute(
                """INSERT OR IGNORE INTO intent_spaces
                       (name, display_name, description, keywords, confidence_threshold)
                   VALUES (?, ?, ?, ?, 0.30)""",
                (name, display_name, description, keywords),
            )

        # Seed bot integrations
        for platform in ("telegram", "slack"):
            conn.execute(
                "INSERT OR IGNORE INTO bot_integrations (platform) VALUES (?)",
                (platform,),
            )
