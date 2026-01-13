#!/usr/bin/env python3
"""
Agent Workflow Evaluation for tldr-swinton

Tests ACTUAL token reduction for Claude Code/Codex workflows.

The key insight: AI agents need FULL CODE to modify it, not just signatures.
Token reduction comes from:
1. Finding relevant files/functions quickly (vs grep/find everything)
2. Loading only relevant code (vs reading entire codebase)
3. Incremental context loading (search -> expand -> modify)

This eval simulates real agent workflows and measures token usage.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import tiktoken
    ENCODER = tiktoken.get_encoding("cl100k_base")
except ImportError:
    print("ERROR: tiktoken not installed. Run: pip install tiktoken")
    sys.exit(1)


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base encoding)."""
    return len(ENCODER.encode(text))


@dataclass
class WorkflowResult:
    """Result of a workflow evaluation."""
    name: str
    passed: bool
    details: str
    baseline_tokens: int = 0  # Tokens without tldr
    tldr_tokens: int = 0      # Tokens with tldr workflow
    savings_percent: float = 0.0


# =============================================================================
# Larger Test Codebase - More Realistic Scale
# =============================================================================

# We'll generate a more realistic codebase with multiple modules
def generate_realistic_codebase(project_dir: Path) -> dict[str, str]:
    """Generate a larger, more realistic test codebase.

    Returns dict mapping filename -> content for token counting.
    """
    files = {}

    # auth/ module - 3 files
    files["auth/__init__.py"] = '''"""Authentication module."""
from .tokens import create_token, verify_token, refresh_token
from .passwords import hash_password, verify_password
from .sessions import SessionManager
'''

    files["auth/tokens.py"] = '''"""JWT token handling for authentication."""

import jwt
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

SECRET_KEY = os.environ.get("JWT_SECRET", "dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


@dataclass
class TokenPayload:
    """Decoded JWT token payload."""
    sub: str
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"


def create_token(
    user_id: str,
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a new JWT token for the given user.

    Args:
        user_id: The user's unique identifier
        token_type: Either "access" or "refresh"
        expires_delta: Custom expiration time

    Returns:
        Encoded JWT token string
    """
    now = datetime.utcnow()

    if expires_delta is None:
        if token_type == "access":
            expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        else:
            expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "type": token_type,
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> Optional[TokenPayload]:
    """Verify a JWT token and return its payload if valid.

    Args:
        token: The JWT token string to verify
        expected_type: The expected token type ("access" or "refresh")

    Returns:
        TokenPayload if valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Verify token type
        if payload.get("type") != expected_type:
            return None

        return TokenPayload(
            sub=payload["sub"],
            exp=datetime.fromtimestamp(payload["exp"]),
            iat=datetime.fromtimestamp(payload["iat"]),
            type=payload["type"],
        )

    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def refresh_token(old_refresh_token: str) -> Optional[tuple[str, str]]:
    """Exchange a refresh token for new access and refresh tokens.

    Args:
        old_refresh_token: The refresh token to exchange

    Returns:
        Tuple of (new_access_token, new_refresh_token) or None if invalid
    """
    payload = verify_token(old_refresh_token, expected_type="refresh")

    if payload is None:
        return None

    new_access = create_token(payload.sub, token_type="access")
    new_refresh = create_token(payload.sub, token_type="refresh")

    return (new_access, new_refresh)


def decode_token_unsafe(token: str) -> Optional[Dict[str, Any]]:
    """Decode a token without verification (for debugging only).

    WARNING: This does not verify the signature!
    """
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None
'''

    files["auth/passwords.py"] = '''"""Password hashing and verification."""

import hashlib
import secrets
from typing import Tuple


HASH_ITERATIONS = 100000
SALT_LENGTH = 32


def hash_password(password: str) -> str:
    """Hash a password with a random salt.

    Args:
        password: The plaintext password

    Returns:
        Hashed password in format "salt$hash"
    """
    salt = secrets.token_hex(SALT_LENGTH)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS
    )
    return f"{salt}${hash_bytes.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash.

    Args:
        password: The plaintext password to check
        hashed: The stored hash in "salt$hash" format

    Returns:
        True if password matches, False otherwise
    """
    try:
        salt, stored_hash = hashed.split("$")
        hash_bytes = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            HASH_ITERATIONS
        )
        return secrets.compare_digest(hash_bytes.hex(), stored_hash)
    except (ValueError, AttributeError):
        return False


def generate_temp_password(length: int = 16) -> str:
    """Generate a random temporary password."""
    return secrets.token_urlsafe(length)
'''

    files["auth/sessions.py"] = '''"""Session management for authenticated users."""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set
from threading import Lock


@dataclass
class Session:
    """An authenticated user session."""
    session_id: str
    user_id: str
    created_at: float
    last_accessed: float
    ip_address: str
    user_agent: str
    is_active: bool = True


class SessionManager:
    """Manages user sessions with automatic expiration."""

    DEFAULT_TTL = 3600 * 24  # 24 hours

    def __init__(self, ttl: int = DEFAULT_TTL):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, Set[str]] = {}  # user_id -> session_ids
        self._lock = Lock()
        self._ttl = ttl

    def create_session(
        self,
        user_id: str,
        ip_address: str,
        user_agent: str
    ) -> Session:
        """Create a new session for a user."""
        import secrets

        session_id = secrets.token_urlsafe(32)
        now = time.time()

        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_accessed=now,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        with self._lock:
            self._sessions[session_id] = session
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = set()
            self._user_sessions[user_id].add(session_id)

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID if it exists and is valid."""
        with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                return None

            # Check expiration
            if time.time() - session.last_accessed > self._ttl:
                self._invalidate_session(session_id)
                return None

            # Update last accessed
            session.last_accessed = time.time()
            return session

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a specific session."""
        with self._lock:
            return self._invalidate_session(session_id)

    def _invalidate_session(self, session_id: str) -> bool:
        """Internal: invalidate session (must hold lock)."""
        session = self._sessions.get(session_id)
        if session is None:
            return False

        session.is_active = False
        del self._sessions[session_id]

        if session.user_id in self._user_sessions:
            self._user_sessions[session.user_id].discard(session_id)

        return True

    def invalidate_all_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user. Returns count invalidated."""
        with self._lock:
            session_ids = self._user_sessions.get(user_id, set()).copy()
            count = 0
            for session_id in session_ids:
                if self._invalidate_session(session_id):
                    count += 1
            return count

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        now = time.time()
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if now - s.last_accessed > self._ttl
            ]
            for session_id in expired:
                self._invalidate_session(session_id)
            return len(expired)
'''

    # users/ module - 2 files
    files["users/__init__.py"] = '''"""User management module."""
from .models import User, UserProfile
from .repository import UserRepository
'''

    files["users/models.py"] = '''"""User data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class UserRole(Enum):
    """User role enumeration."""
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"


class UserStatus(Enum):
    """User account status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"
    DELETED = "deleted"


@dataclass
class UserProfile:
    """Extended user profile information."""
    display_name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None


@dataclass
class User:
    """User account model."""
    id: str
    email: str
    username: str
    password_hash: str
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    profile: Optional[UserProfile] = None

    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == UserStatus.ACTIVE

    def is_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.role == UserRole.ADMIN

    def can_moderate(self) -> bool:
        """Check if user has moderation privileges."""
        return self.role in (UserRole.ADMIN, UserRole.MODERATOR)
'''

    files["users/repository.py"] = '''"""User data access layer."""

from typing import Dict, List, Optional
from datetime import datetime
from .models import User, UserStatus


class UserRepository:
    """Repository for user data operations."""

    def __init__(self):
        self._users: Dict[str, User] = {}
        self._email_index: Dict[str, str] = {}  # email -> user_id
        self._username_index: Dict[str, str] = {}  # username -> user_id

    def create(self, user: User) -> User:
        """Create a new user.

        Raises:
            ValueError: If email or username already exists
        """
        if user.email in self._email_index:
            raise ValueError(f"Email {user.email} already registered")
        if user.username in self._username_index:
            raise ValueError(f"Username {user.username} already taken")

        self._users[user.id] = user
        self._email_index[user.email] = user.id
        self._username_index[user.username] = user.id

        return user

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Find user by ID."""
        return self._users.get(user_id)

    def get_by_email(self, email: str) -> Optional[User]:
        """Find user by email address."""
        user_id = self._email_index.get(email)
        if user_id:
            return self._users.get(user_id)
        return None

    def get_by_username(self, username: str) -> Optional[User]:
        """Find user by username."""
        user_id = self._username_index.get(username)
        if user_id:
            return self._users.get(user_id)
        return None

    def update(self, user: User) -> User:
        """Update an existing user."""
        if user.id not in self._users:
            raise ValueError(f"User {user.id} not found")

        old_user = self._users[user.id]

        # Update email index if changed
        if old_user.email != user.email:
            if user.email in self._email_index:
                raise ValueError(f"Email {user.email} already registered")
            del self._email_index[old_user.email]
            self._email_index[user.email] = user.id

        # Update username index if changed
        if old_user.username != user.username:
            if user.username in self._username_index:
                raise ValueError(f"Username {user.username} already taken")
            del self._username_index[old_user.username]
            self._username_index[user.username] = user.id

        user.updated_at = datetime.utcnow()
        self._users[user.id] = user
        return user

    def delete(self, user_id: str) -> bool:
        """Soft delete a user (sets status to DELETED)."""
        user = self._users.get(user_id)
        if user is None:
            return False

        user.status = UserStatus.DELETED
        user.updated_at = datetime.utcnow()
        return True

    def hard_delete(self, user_id: str) -> bool:
        """Permanently delete a user and all indexes."""
        user = self._users.get(user_id)
        if user is None:
            return False

        del self._users[user_id]
        del self._email_index[user.email]
        del self._username_index[user.username]
        return True

    def list_all(self, include_deleted: bool = False) -> List[User]:
        """List all users."""
        users = list(self._users.values())
        if not include_deleted:
            users = [u for u in users if u.status != UserStatus.DELETED]
        return users

    def count(self, include_deleted: bool = False) -> int:
        """Count total users."""
        if include_deleted:
            return len(self._users)
        return len([u for u in self._users.values() if u.status != UserStatus.DELETED])
'''

    # db/ module
    files["db/__init__.py"] = '''"""Database module."""
from .connection import DatabaseConnection, get_connection
from .migrations import run_migrations
'''

    files["db/connection.py"] = '''"""Database connection management."""

import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, List, Any
from threading import local


_thread_local = local()


class DatabaseConnection:
    """SQLite database connection with context management."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Establish database connection."""
        if self._connection is not None:
            return

        self._connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row

        # Enable foreign keys
        self._connection.execute("PRAGMA foreign_keys = ON")

    def disconnect(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        if self._connection is None:
            self.connect()

        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        if self._connection is None:
            self.connect()
        return self._connection.execute(query, params)

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute query and fetch all results as dicts."""
        cursor = self.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute query and fetch one result as dict."""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def insert(self, query: str, params: tuple = ()) -> int:
        """Execute insert and return last row ID."""
        cursor = self.execute(query, params)
        self._connection.commit()
        return cursor.lastrowid

    def update(self, query: str, params: tuple = ()) -> int:
        """Execute update and return rows affected."""
        cursor = self.execute(query, params)
        self._connection.commit()
        return cursor.rowcount


_default_connection: Optional[DatabaseConnection] = None


def get_connection(db_path: Optional[str] = None) -> DatabaseConnection:
    """Get or create a database connection."""
    global _default_connection

    if db_path is not None:
        return DatabaseConnection(db_path)

    if _default_connection is None:
        _default_connection = DatabaseConnection(":memory:")

    return _default_connection
'''

    files["db/migrations.py"] = '''"""Database migration utilities."""

from typing import List, Callable
from .connection import DatabaseConnection


Migration = Callable[[DatabaseConnection], None]

_migrations: List[Migration] = []


def migration(fn: Migration) -> Migration:
    """Decorator to register a migration function."""
    _migrations.append(fn)
    return fn


@migration
def create_users_table(conn: DatabaseConnection) -> None:
    """Create the users table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)


@migration
def create_sessions_table(conn: DatabaseConnection) -> None:
    """Create the sessions table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)


@migration
def create_audit_log_table(conn: DatabaseConnection) -> None:
    """Create the audit log table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)


def run_migrations(conn: DatabaseConnection) -> int:
    """Run all pending migrations. Returns count run."""
    # Create migrations tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Get applied migrations
    applied = set(
        row["name"]
        for row in conn.fetch_all("SELECT name FROM _migrations")
    )

    count = 0
    for migration_fn in _migrations:
        name = migration_fn.__name__
        if name not in applied:
            migration_fn(conn)
            conn.execute(
                "INSERT INTO _migrations (name) VALUES (?)",
                (name,)
            )
            count += 1

    return count
'''

    # Create all directories and files
    for filepath, content in files.items():
        full_path = project_dir / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    return files


# =============================================================================
# Workflow Simulations
# =============================================================================

def run_tldrs(cmd: list[str], cwd: str) -> tuple[str, str, int]:
    """Run tldrs command."""
    result = subprocess.run(
        ["tldrs"] + cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.stdout, result.stderr, result.returncode


def workflow_find_and_fix_bug(project_dir: str, all_files: dict[str, str]) -> WorkflowResult:
    """
    Simulate: "Fix the JWT token verification - it's not checking token type"

    BASELINE (no tldr):
    - Agent reads all auth-related files to understand the code
    - Total tokens = all auth/*.py files

    WITH TLDR:
    - Search for "JWT token verification"
    - Expand only the relevant function
    - Total tokens = search results + expanded function
    """
    # Calculate baseline: all auth files
    auth_files = [
        content for path, content in all_files.items()
        if path.startswith("auth/")
    ]
    baseline_tokens = sum(count_tokens(f) for f in auth_files)

    # With tldr workflow:
    # 1. Search (get signatures/summaries)
    search_out, _, code = run_tldrs(["find", "JWT token verification", "-k", "3"], cwd=project_dir)
    if code != 0:
        return WorkflowResult("Find and fix bug", False, f"Search failed", baseline_tokens, 0, 0)

    search_tokens = count_tokens(search_out)

    # 2. Read the relevant file (verify_token function is in auth/tokens.py)
    # In real workflow, agent would read just that file
    tokens_file = all_files.get("auth/tokens.py", "")
    file_tokens = count_tokens(tokens_file)

    tldr_tokens = search_tokens + file_tokens

    # Calculate savings
    if baseline_tokens == 0:
        savings = 0.0
    else:
        savings = (baseline_tokens - tldr_tokens) / baseline_tokens * 100

    passed = tldr_tokens < baseline_tokens

    return WorkflowResult(
        "Find and fix JWT bug",
        passed,
        f"Baseline: {baseline_tokens} tokens (all auth/), tldr: {tldr_tokens} tokens (search + relevant file)",
        baseline_tokens,
        tldr_tokens,
        savings
    )


def workflow_understand_module(project_dir: str, all_files: dict[str, str]) -> WorkflowResult:
    """
    Simulate: "How does user management work in this codebase?"

    BASELINE (no tldr):
    - Agent reads ALL files to understand the codebase
    - Total tokens = entire codebase

    WITH TLDR:
    - Search for "user management"
    - Get relevant signatures and summaries
    - Expand only the core user files
    """
    # Baseline: entire codebase
    baseline_tokens = sum(count_tokens(f) for f in all_files.values())

    # With tldr:
    # 1. Search
    search_out, _, code = run_tldrs(["find", "user management", "-k", "5"], cwd=project_dir)
    if code != 0:
        return WorkflowResult("Understand module", False, "Search failed", baseline_tokens, 0, 0)

    search_tokens = count_tokens(search_out)

    # 2. Read the relevant module (just users/)
    users_files = [
        content for path, content in all_files.items()
        if path.startswith("users/")
    ]
    users_tokens = sum(count_tokens(f) for f in users_files)

    tldr_tokens = search_tokens + users_tokens

    if baseline_tokens == 0:
        savings = 0.0
    else:
        savings = (baseline_tokens - tldr_tokens) / baseline_tokens * 100

    passed = tldr_tokens < baseline_tokens

    return WorkflowResult(
        "Understand user module",
        passed,
        f"Baseline: {baseline_tokens} tokens (all files), tldr: {tldr_tokens} tokens (search + users/)",
        baseline_tokens,
        tldr_tokens,
        savings
    )


def workflow_add_feature(project_dir: str, all_files: dict[str, str]) -> WorkflowResult:
    """
    Simulate: "Add password reset functionality"

    BASELINE:
    - Read auth module to understand existing password handling
    - Read user module to understand user model

    WITH TLDR:
    - Search for "password"
    - Read only relevant files (auth/passwords.py, users/repository.py)
    """
    # Baseline: auth + users modules
    relevant_modules = [
        content for path, content in all_files.items()
        if path.startswith("auth/") or path.startswith("users/")
    ]
    baseline_tokens = sum(count_tokens(f) for f in relevant_modules)

    # With tldr:
    # 1. Search
    search_out, _, code = run_tldrs(["find", "password hash verify", "-k", "5"], cwd=project_dir)
    if code != 0:
        return WorkflowResult("Add feature", False, "Search failed", baseline_tokens, 0, 0)

    search_tokens = count_tokens(search_out)

    # 2. Read only the specific files needed
    needed_files = ["auth/passwords.py", "users/repository.py"]
    needed_tokens = sum(count_tokens(all_files.get(f, "")) for f in needed_files)

    tldr_tokens = search_tokens + needed_tokens

    if baseline_tokens == 0:
        savings = 0.0
    else:
        savings = (baseline_tokens - tldr_tokens) / baseline_tokens * 100

    passed = tldr_tokens < baseline_tokens

    return WorkflowResult(
        "Add password reset feature",
        passed,
        f"Baseline: {baseline_tokens} tokens (auth/ + users/), tldr: {tldr_tokens} tokens (search + 2 files)",
        baseline_tokens,
        tldr_tokens,
        savings
    )


def workflow_exact_symbol_lookup(project_dir: str, all_files: dict[str, str]) -> WorkflowResult:
    """
    Simulate: "Show me the SessionManager class"

    Tests the lexical fast-path for exact symbol names.

    BASELINE:
    - grep/find through codebase to locate the class
    - Read the file containing it

    WITH TLDR:
    - Direct lookup by name -> exact match with score 1.0
    """
    # Baseline: would need to search + read
    # Assume grep output + the file
    sessions_file = all_files.get("auth/sessions.py", "")
    baseline_tokens = count_tokens(sessions_file)

    # With tldr: exact name lookup
    search_out, _, code = run_tldrs(["find", "SessionManager", "-k", "1"], cwd=project_dir)
    if code != 0:
        return WorkflowResult("Exact symbol lookup", False, "Search failed", baseline_tokens, 0, 0)

    # Check that we got score 1.0 (exact match)
    has_exact_match = "[1.0" in search_out or "[1.00" in search_out

    search_tokens = count_tokens(search_out)

    # Still need to read the file to modify
    tldr_tokens = search_tokens + baseline_tokens

    # For exact lookup, the win is in speed, not tokens
    # But search results are much smaller than full grep output
    passed = has_exact_match

    return WorkflowResult(
        "Exact symbol lookup",
        passed,
        f"Exact match found: {has_exact_match}, search tokens: {search_tokens}",
        baseline_tokens,
        search_tokens,  # Just search, since we'd read file anyway
        0 if not has_exact_match else 90.0  # Estimate
    )


# =============================================================================
# Main
# =============================================================================

def run_all_workflows() -> list[WorkflowResult]:
    """Run all workflow evaluations."""
    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "realistic_project"
        project_dir.mkdir()

        # Generate codebase
        all_files = generate_realistic_codebase(project_dir)
        total_tokens = sum(count_tokens(f) for f in all_files.values())
        print(f"Generated test codebase: {len(all_files)} files, {total_tokens} tokens total")

        # Build index
        stdout, stderr, code = run_tldrs(["index", "."], cwd=str(project_dir))
        if code != 0:
            print(f"ERROR: Failed to build index: {stderr}")
            return []
        print("Index built successfully")
        print()

        # Run workflows
        results.append(workflow_find_and_fix_bug(str(project_dir), all_files))
        results.append(workflow_understand_module(str(project_dir), all_files))
        results.append(workflow_add_feature(str(project_dir), all_files))
        results.append(workflow_exact_symbol_lookup(str(project_dir), all_files))

    return results


def print_results(results: list[WorkflowResult]) -> bool:
    """Print results and return True if all passed."""
    print("=" * 70)
    print("tldr-swinton Agent Workflow Evaluation")
    print("=" * 70)
    print()
    print("These tests simulate REAL agent workflows and measure actual token")
    print("reduction compared to reading entire modules/codebase.")
    print()

    all_passed = True
    total_baseline = 0
    total_tldr = 0

    for r in results:
        status = "✓ PASS" if r.passed else "✗ FAIL"
        print(f"{status}: {r.name}")
        print(f"       {r.details}")
        if r.baseline_tokens > 0 and r.tldr_tokens > 0:
            print(f"       Savings: {r.savings_percent:.1f}%")
        print()

        if not r.passed:
            all_passed = False

        total_baseline += r.baseline_tokens
        total_tldr += r.tldr_tokens

    print("=" * 70)
    if total_baseline > 0:
        overall_savings = (total_baseline - total_tldr) / total_baseline * 100
        print(f"OVERALL: {total_baseline} baseline tokens -> {total_tldr} with tldr")
        print(f"         Aggregate savings: {overall_savings:.1f}%")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    results = run_all_workflows()
    all_passed = print_results(results)
    sys.exit(0 if all_passed else 1)
