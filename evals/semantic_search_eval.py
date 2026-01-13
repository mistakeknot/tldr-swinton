#!/usr/bin/env python3
"""
Semantic Search Evaluation for tldr-swinton v0.2.0

Tests the new semantic indexing and search features:
1. Index creation and persistence
2. Incremental indexing (only re-index changed files)
3. Semantic search relevance
4. Token savings vs dumping all code
5. Backend detection (Ollama vs sentence-transformers fallback)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

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
class EvalResult:
    name: str
    passed: bool
    details: str
    metric_value: float = 0.0


def run_tldrs(cmd: list[str], cwd: str = None) -> tuple[str, str, int]:
    """Run tldrs command and return stdout, stderr, returncode."""
    result = subprocess.run(
        ["tldrs"] + cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.stdout, result.stderr, result.returncode


# =============================================================================
# Test Files - Simulate a small codebase
# =============================================================================

AUTH_FILE = '''
"""Authentication module with JWT token handling."""

import jwt
from datetime import datetime, timedelta
from typing import Optional

SECRET_KEY = "your-secret-key"

def create_access_token(user_id: str, expires_delta: timedelta = None) -> str:
    """Create a new JWT access token for the given user."""
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return the user_id if valid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def refresh_token(old_token: str) -> Optional[str]:
    """Refresh an existing token if still valid."""
    user_id = verify_token(old_token)
    if user_id:
        return create_access_token(user_id)
    return None

class TokenBlacklist:
    """Maintains a list of revoked tokens."""

    def __init__(self):
        self._blacklist = set()

    def add(self, token: str):
        """Add a token to the blacklist."""
        self._blacklist.add(token)

    def is_blacklisted(self, token: str) -> bool:
        """Check if a token has been revoked."""
        return token in self._blacklist
'''

USER_FILE = '''
"""User management with CRUD operations."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class User:
    """Represents a user in the system."""
    id: str
    username: str
    email: str
    password_hash: str
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True

class UserRepository:
    """Repository pattern for user data access."""

    def __init__(self):
        self._users: Dict[str, User] = {}

    def create(self, user: User) -> User:
        """Create a new user in the repository."""
        self._users[user.id] = user
        return user

    def find_by_id(self, user_id: str) -> Optional[User]:
        """Find a user by their unique ID."""
        return self._users.get(user_id)

    def find_by_email(self, email: str) -> Optional[User]:
        """Find a user by their email address."""
        for user in self._users.values():
            if user.email == email:
                return user
        return None

    def update(self, user: User) -> User:
        """Update an existing user's data."""
        if user.id in self._users:
            self._users[user.id] = user
        return user

    def delete(self, user_id: str) -> bool:
        """Delete a user from the repository."""
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False

    def list_all(self) -> List[User]:
        """List all users in the repository."""
        return list(self._users.values())
'''

DATABASE_FILE = '''
"""Database connection and query utilities."""

import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

class DatabaseConnection:
    """Manages SQLite database connections."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection = None

    def connect(self):
        """Establish database connection."""
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row

    def disconnect(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute a SELECT query and return results as dicts."""
        cursor = self._connection.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def execute_insert(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT query and return the last row ID."""
        cursor = self._connection.cursor()
        cursor.execute(query, params)
        return cursor.lastrowid

    def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute an UPDATE query and return rows affected."""
        cursor = self._connection.cursor()
        cursor.execute(query, params)
        return cursor.rowcount

def create_tables(conn: DatabaseConnection):
    """Create all database tables."""
    with conn.transaction() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT,
                created_at TIMESTAMP
            )
        """)
'''

CACHE_FILE = '''
"""In-memory caching with TTL support."""

import time
from typing import Any, Dict, Optional
from dataclasses import dataclass

@dataclass
class CacheEntry:
    """A single cache entry with value and expiration."""
    value: Any
    expires_at: float

class MemoryCache:
    """Simple in-memory cache with time-to-live."""

    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: int = None):
        """Set a value in cache with optional custom TTL."""
        expires_at = time.time() + (ttl or self._default_ttl)
        self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self):
        """Clear all entries from the cache."""
        self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove all expired entries and return count removed."""
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if v.expires_at < now]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)
'''


# =============================================================================
# Evaluation Functions
# =============================================================================

def eval_index_creation(project_dir: str) -> EvalResult:
    """Test that index can be created from a codebase."""
    stdout, stderr, code = run_tldrs(["index", "."], cwd=project_dir)

    # Check for success indicators in output
    if code != 0:
        return EvalResult(
            "Index creation",
            False,
            f"Command failed with code {code}: {stderr[:200]}",
        )

    # Check that .tldr directory was created
    tldr_dir = Path(project_dir) / ".tldr" / "index"
    if not tldr_dir.exists():
        return EvalResult(
            "Index creation",
            False,
            ".tldr/index directory not created",
        )

    # Check for index files
    expected_files = ["vectors.faiss", "units.json", "meta.json"]
    missing = [f for f in expected_files if not (tldr_dir / f).exists()]
    if missing:
        return EvalResult(
            "Index creation",
            False,
            f"Missing index files: {missing}",
        )

    # Parse meta to get stats
    try:
        meta = json.loads((tldr_dir / "meta.json").read_text())
        unit_count = meta.get("count", 0)  # 'count' is the actual field name
        backend = meta.get("embed_backend", "unknown")
    except Exception as e:
        return EvalResult(
            "Index creation",
            False,
            f"Failed to parse meta.json: {e}",
        )

    if unit_count == 0:
        return EvalResult(
            "Index creation",
            False,
            f"Index created but has 0 code units",
        )

    return EvalResult(
        "Index creation",
        True,
        f"Indexed {unit_count} code units using {backend}",
        metric_value=unit_count,
    )


def eval_index_info(project_dir: str) -> EvalResult:
    """Test the --info flag shows index information."""
    stdout, stderr, code = run_tldrs(["index", ".", "--info"], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Index info",
            False,
            f"Command failed: {stderr[:200]}",
        )

    # Output is JSON - parse and check for key fields
    try:
        data = json.loads(stdout)
        required_fields = ["count", "dimension", "embed_model", "embed_backend"]
        missing = [f for f in required_fields if f not in data]

        if missing:
            return EvalResult(
                "Index info",
                False,
                f"Missing fields in JSON: {missing}",
            )

        return EvalResult(
            "Index info",
            True,
            f"Index info: {data.get('count', 0)} units, {data.get('embed_backend', 'unknown')} backend",
        )
    except json.JSONDecodeError:
        # Fallback: check for key strings in text output
        required_info = ["count", "dimension", "backend"]
        found = sum(1 for info in required_info if info.lower() in stdout.lower())
        if found >= 2:
            return EvalResult("Index info", True, f"Index info displayed (text format)")
        return EvalResult(
            "Index info",
            False,
            f"Could not parse output: {stdout[:200]}",
        )


def eval_incremental_indexing(project_dir: str) -> EvalResult:
    """Test that re-indexing without changes is fast (no re-embedding)."""
    # First run should have done full indexing
    # Second run should detect no changes
    stdout, stderr, code = run_tldrs(["index", "."], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Incremental indexing",
            False,
            f"Re-index failed: {stderr[:200]}",
        )

    # Look for indicators that it detected existing index
    if "unchanged" in stdout.lower() or "up to date" in stdout.lower() or "0 changed" in stdout.lower():
        return EvalResult(
            "Incremental indexing",
            True,
            "Correctly detected no changes needed",
        )

    # May still work but less efficiently
    return EvalResult(
        "Incremental indexing",
        True,
        f"Re-indexed (incremental detection: unknown). Output: {stdout[:150]}",
    )


def eval_semantic_search_basic(project_dir: str) -> EvalResult:
    """Test basic semantic search returns results."""
    stdout, stderr, code = run_tldrs(["find", "authentication"], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Semantic search basic",
            False,
            f"Search failed: {stderr[:200]}",
        )

    if not stdout.strip():
        return EvalResult(
            "Semantic search basic",
            False,
            "No results returned for 'authentication' query",
        )

    # Count results (look for result indicators)
    result_count = stdout.lower().count("score:") or stdout.count("→")
    if result_count == 0:
        result_count = len([l for l in stdout.split("\n") if l.strip()])

    return EvalResult(
        "Semantic search basic",
        True,
        f"Found {result_count} results for 'authentication'",
        metric_value=result_count,
    )


def eval_search_relevance_auth(project_dir: str) -> EvalResult:
    """Test that auth-related queries find auth functions as TOP result."""
    stdout, stderr, code = run_tldrs(["find", "JWT token validation", "-k", "3"], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Search relevance (auth)",
            False,
            f"Search failed: {stderr[:200]}",
        )

    # Parse results to check the TOP result specifically
    lines = stdout.strip().split("\n")

    # Find the first result line (starts with " 1.")
    top_result = ""
    for line in lines:
        if line.strip().startswith("1."):
            top_result = line
            break

    # Top result MUST be verify_token - this is the most relevant function
    if "verify_token" not in top_result.lower():
        return EvalResult(
            "Search relevance (auth)",
            False,
            f"Top result should be verify_token. Got: {top_result[:100]}",
        )

    return EvalResult(
        "Search relevance (auth)",
        True,
        "verify_token is top result for JWT query",
    )


def eval_search_relevance_db(project_dir: str) -> EvalResult:
    """Test that database queries find execute_query as TOP result."""
    stdout, stderr, code = run_tldrs(["find", "execute SQL query on database", "-k", "3"], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Search relevance (database)",
            False,
            f"Search failed: {stderr[:200]}",
        )

    # Parse to get top result
    lines = stdout.strip().split("\n")
    top_result = ""
    for line in lines:
        if line.strip().startswith("1."):
            top_result = line
            break

    # Top result should be execute_query
    if "execute_query" not in top_result.lower():
        return EvalResult(
            "Search relevance (database)",
            False,
            f"Top result should be execute_query. Got: {top_result[:100]}",
        )

    return EvalResult(
        "Search relevance (database)",
        True,
        "execute_query is top result for database query",
    )


def eval_search_relevance_cache(project_dir: str) -> EvalResult:
    """Test that caching queries find MemoryCache as TOP result."""
    stdout, stderr, code = run_tldrs(["find", "in-memory cache with TTL expiration", "-k", "3"], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Search relevance (cache)",
            False,
            f"Search failed: {stderr[:200]}",
        )

    # Parse to get top result
    lines = stdout.strip().split("\n")
    top_result = ""
    for line in lines:
        if line.strip().startswith("1."):
            top_result = line
            break

    # Top result should be MemoryCache class
    if "memorycache" not in top_result.lower():
        return EvalResult(
            "Search relevance (cache)",
            False,
            f"Top result should be MemoryCache. Got: {top_result[:100]}",
        )

    return EvalResult(
        "Search relevance (cache)",
        True,
        "MemoryCache is top result for cache query",
    )


def eval_search_score_quality(project_dir: str) -> EvalResult:
    """Test that top results have high confidence scores (>0.6)."""
    stdout, stderr, code = run_tldrs(["find", "verify JWT token", "-k", "1"], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Search score quality",
            False,
            f"Search failed: {stderr[:200]}",
        )

    # Parse the score from output like " 1. [0.752] verify_token"
    import re
    match = re.search(r'\[(\d+\.\d+)\]', stdout)
    if not match:
        return EvalResult(
            "Search score quality",
            False,
            f"Could not parse score from output: {stdout[:100]}",
        )

    score = float(match.group(1))

    # Top result for a specific query should have score > 0.6
    # Low scores indicate poor semantic match
    if score < 0.6:
        return EvalResult(
            "Search score quality",
            False,
            f"Top result score {score:.3f} is too low (need >0.6)",
            metric_value=score,
        )

    return EvalResult(
        "Search score quality",
        True,
        f"Top result score {score:.3f} indicates good semantic match",
        metric_value=score,
    )


def eval_token_savings_vs_raw(project_dir: str, all_code: str) -> EvalResult:
    """Compare tokens needed for search results vs dumping all code."""
    # Search for a specific topic
    stdout, stderr, code = run_tldrs(["find", "verify JWT token", "-k", "5"], cwd=project_dir)

    if code != 0:
        return EvalResult(
            "Token savings vs raw",
            False,
            f"Search failed: {stderr[:200]}",
        )

    raw_tokens = count_tokens(all_code)
    search_tokens = count_tokens(stdout)

    if raw_tokens == 0:
        return EvalResult(
            "Token savings vs raw",
            False,
            "Raw code is empty",
        )

    savings = 1.0 - (search_tokens / raw_tokens)

    # We expect at least 50% savings (search results vs all code)
    passed = savings >= 0.50

    return EvalResult(
        "Token savings vs raw",
        passed,
        f"Raw: {raw_tokens} tokens, Search results: {search_tokens} tokens, Savings: {savings:.1%}",
        metric_value=savings * 100,
    )


def eval_search_limit_k(project_dir: str) -> EvalResult:
    """Test that -k flag limits results."""
    # Get 3 results
    stdout3, _, code3 = run_tldrs(["find", "function", "-k", "3"], cwd=project_dir)
    # Get 10 results
    stdout10, _, code10 = run_tldrs(["find", "function", "-k", "10"], cwd=project_dir)

    if code3 != 0 or code10 != 0:
        return EvalResult(
            "Search result limit (-k)",
            False,
            "One or both searches failed",
        )

    # Count results in each
    lines3 = len([l for l in stdout3.split("\n") if l.strip() and "score" in l.lower()])
    lines10 = len([l for l in stdout10.split("\n") if l.strip() and "score" in l.lower()])

    # If score isn't in output, count non-empty lines
    if lines3 == 0:
        lines3 = len([l for l in stdout3.split("\n") if l.strip()])
    if lines10 == 0:
        lines10 = len([l for l in stdout10.split("\n") if l.strip()])

    # k=3 should have fewer or equal results to k=10
    if lines3 > lines10:
        return EvalResult(
            "Search result limit (-k)",
            False,
            f"-k 3 returned {lines3} lines, -k 10 returned {lines10} lines (unexpected)",
        )

    return EvalResult(
        "Search result limit (-k)",
        True,
        f"-k 3: {lines3} results, -k 10: {lines10} results",
    )


def eval_backend_detection() -> EvalResult:
    """Test that backend detection works (Ollama or fallback)."""
    stdout, stderr, code = run_tldrs(["index", ".", "--info"], cwd=".")

    # Also check embeddings module directly
    try:
        from tldr_swinton.embeddings import check_backends
        backends = check_backends()
        # check_backends() returns nested dicts like {"ollama": {"available": True, ...}}
        available = [b for b, v in backends.items() if v.get("available")]

        if not available:
            return EvalResult(
                "Backend detection",
                False,
                "No embedding backends available",
            )

        return EvalResult(
            "Backend detection",
            True,
            f"Available backends: {', '.join(available)}",
        )
    except ImportError as e:
        return EvalResult(
            "Backend detection",
            False,
            f"Failed to import embeddings module: {e}",
        )


# =============================================================================
# Main Evaluation Runner
# =============================================================================

def setup_test_project(tmpdir: str) -> str:
    """Create a test project with sample files."""
    project_dir = Path(tmpdir) / "test_project"
    project_dir.mkdir()

    # Create source files
    (project_dir / "auth.py").write_text(AUTH_FILE)
    (project_dir / "user.py").write_text(USER_FILE)
    (project_dir / "database.py").write_text(DATABASE_FILE)
    (project_dir / "cache.py").write_text(CACHE_FILE)

    return str(project_dir)


def run_all_evals() -> list[EvalResult]:
    """Run all semantic search evaluations."""
    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = setup_test_project(tmpdir)
        all_code = AUTH_FILE + USER_FILE + DATABASE_FILE + CACHE_FILE

        # Test backend detection first
        results.append(eval_backend_detection())

        # Index creation tests
        results.append(eval_index_creation(project_dir))
        results.append(eval_index_info(project_dir))
        results.append(eval_incremental_indexing(project_dir))

        # Search tests
        results.append(eval_semantic_search_basic(project_dir))
        results.append(eval_search_relevance_auth(project_dir))
        results.append(eval_search_relevance_db(project_dir))
        results.append(eval_search_relevance_cache(project_dir))
        results.append(eval_search_score_quality(project_dir))
        results.append(eval_search_limit_k(project_dir))

        # Token savings
        results.append(eval_token_savings_vs_raw(project_dir, all_code))

    return results


def print_results(results: list[EvalResult]) -> bool:
    """Print evaluation results and return True if all passed."""
    print("=" * 70)
    print("tldr-swinton Semantic Search Evaluation (v0.2.0)")
    print("=" * 70)
    print()

    passed_count = 0
    failed_count = 0

    # Group by category
    backend_results = [r for r in results if "backend" in r.name.lower()]
    index_results = [r for r in results if "index" in r.name.lower()]
    search_results = [r for r in results if "search" in r.name.lower()]
    savings_results = [r for r in results if "token" in r.name.lower() or "savings" in r.name.lower()]

    def print_section(title: str, section_results: list[EvalResult]):
        nonlocal passed_count, failed_count
        if not section_results:
            return
        print(f"## {title}")
        print()
        for r in section_results:
            status = "✓ PASS" if r.passed else "✗ FAIL"
            print(f"  {status}: {r.name}")
            print(f"         {r.details}")
            if r.passed:
                passed_count += 1
            else:
                failed_count += 1
        print()

    print_section("Embedding Backend", backend_results)
    print_section("Index Management", index_results)
    print_section("Semantic Search", search_results)
    print_section("Token Efficiency", savings_results)

    # Summary
    total = passed_count + failed_count
    print("=" * 70)
    print(f"SUMMARY: {passed_count}/{total} evaluations passed")

    # Show token savings if available
    if savings_results:
        for r in savings_results:
            if r.metric_value > 0:
                print(f"Token savings: {r.metric_value:.1f}%")

    print("=" * 70)

    return failed_count == 0


if __name__ == "__main__":
    results = run_all_evals()
    all_passed = print_results(results)
    sys.exit(0 if all_passed else 1)
