#!/usr/bin/env python3
"""
Token Efficiency Evaluation for tldr-swinton

Measures token savings compared to raw file content for various use cases.
Claims to verify:
1. Token savings for structure/codemap output vs raw files
2. Language-appropriate signatures (TypeScript, Rust)
3. Clean function names (no export/async prefixes)
4. Single file support
"""

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import tiktoken
    ENCODER = tiktoken.get_encoding("cl100k_base")  # GPT-4/Claude encoding
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
    raw_tokens: int = 0
    tldr_tokens: int = 0
    savings_pct: float = 0.0


def run_tldrs(cmd: list[str]) -> str:
    """Run tldrs command and return output."""
    result = subprocess.run(
        ["tldrs"] + cmd,
        capture_output=True,
        text=True,
    )
    return result.stdout


# =============================================================================
# Test Files
# =============================================================================

TYPESCRIPT_FILE = '''
import { invoke } from '@tauri-apps/api/core';
import { useState, useEffect, useCallback } from 'react';

interface UserData {
    id: string;
    name: string;
    email: string;
    createdAt: Date;
}

interface ApiResponse<T> {
    data: T;
    error?: string;
    status: number;
}

/**
 * Fetches user data from the backend API.
 * @param userId - The unique identifier of the user
 * @returns Promise resolving to user data or null if not found
 */
export async function fetchUserData(userId: string): Promise<UserData | null> {
    try {
        const response = await invoke<ApiResponse<UserData>>('get_user', { userId });
        if (response.error) {
            console.error('Failed to fetch user:', response.error);
            return null;
        }
        return response.data;
    } catch (error) {
        console.error('API call failed:', error);
        return null;
    }
}

export async function updateUserProfile(
    userId: string,
    updates: Partial<UserData>
): Promise<boolean> {
    try {
        const response = await invoke<ApiResponse<void>>('update_user', {
            userId,
            updates,
        });
        return response.status === 200;
    } catch (error) {
        console.error('Update failed:', error);
        return false;
    }
}

export function useUserData(userId: string) {
    const [user, setUser] = useState<UserData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const data = await fetchUserData(userId);
            setUser(data);
            setError(null);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { user, loading, error, refresh };
}

export default function formatUserName(user: UserData): string {
    return `${user.name} <${user.email}>`;
}
'''

RUST_FILE = '''
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Represents a cached item with expiration
#[derive(Debug, Clone)]
pub struct CacheEntry<T> {
    pub value: T,
    pub expires_at: u64,
}

/// Thread-safe LRU cache implementation
pub struct Cache<K, V> {
    data: Arc<RwLock<HashMap<K, CacheEntry<V>>>>,
    max_size: usize,
    ttl_seconds: u64,
}

impl<K, V> Cache<K, V>
where
    K: std::hash::Hash + Eq + Clone,
    V: Clone,
{
    /// Creates a new cache with specified capacity and TTL
    pub fn new(max_size: usize, ttl_seconds: u64) -> Self {
        Self {
            data: Arc::new(RwLock::new(HashMap::new())),
            max_size,
            ttl_seconds,
        }
    }

    /// Retrieves a value from the cache if it exists and hasn't expired
    pub async fn get(&self, key: &K) -> Option<V> {
        let data = self.data.read().await;
        if let Some(entry) = data.get(key) {
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs();
            if entry.expires_at > now {
                return Some(entry.value.clone());
            }
        }
        None
    }

    /// Inserts a value into the cache with automatic expiration
    pub async fn set(&self, key: K, value: V) {
        let mut data = self.data.write().await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();

        // Evict if at capacity
        if data.len() >= self.max_size {
            self.evict_expired(&mut data, now);
        }

        data.insert(key, CacheEntry {
            value,
            expires_at: now + self.ttl_seconds,
        });
    }

    /// Removes expired entries from the cache
    fn evict_expired(&self, data: &mut HashMap<K, CacheEntry<V>>, now: u64) {
        data.retain(|_, entry| entry.expires_at > now);
    }

    /// Returns the current number of entries in the cache
    pub async fn len(&self) -> usize {
        self.data.read().await.len()
    }

    /// Checks if the cache is empty
    pub async fn is_empty(&self) -> bool {
        self.data.read().await.is_empty()
    }
}

/// Clears all entries from the cache
pub async fn clear_cache<K, V>(cache: &Cache<K, V>)
where
    K: std::hash::Hash + Eq + Clone,
    V: Clone,
{
    let mut data = cache.data.write().await;
    data.clear();
}
'''

PYTHON_FILE = '''
"""
User authentication and session management module.

Provides secure authentication, token generation, and session handling
for the application's user management system.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


@dataclass
class User:
    """Represents an authenticated user."""
    id: str
    username: str
    email: str
    password_hash: str
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    is_active: bool = True


@dataclass
class Session:
    """Represents an active user session."""
    token: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class SessionManager:
    """Manages user sessions with automatic expiration."""

    def __init__(self, session_ttl_hours: int = 24):
        self._sessions: Dict[str, Session] = {}
        self._ttl = timedelta(hours=session_ttl_hours)

    def create_session(self, user: User) -> Session:
        """Creates a new session for the given user."""
        token = secrets.token_urlsafe(32)
        now = datetime.now()
        session = Session(
            token=token,
            user_id=user.id,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._sessions[token] = session
        return session

    def validate_session(self, token: str) -> Optional[Session]:
        """Validates a session token and returns the session if valid."""
        session = self._sessions.get(token)
        if session is None:
            return None
        if datetime.now() > session.expires_at:
            del self._sessions[token]
            return None
        return session

    def invalidate_session(self, token: str) -> bool:
        """Invalidates a session, logging the user out."""
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False

    def cleanup_expired(self) -> int:
        """Removes all expired sessions and returns count removed."""
        now = datetime.now()
        expired = [t for t, s in self._sessions.items() if s.expires_at < now]
        for token in expired:
            del self._sessions[token]
        return len(expired)


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hashes a password with a salt using SHA-256."""
    if salt is None:
        salt = secrets.token_hex(16)
    combined = f"{salt}{password}"
    hashed = hashlib.sha256(combined.encode()).hexdigest()
    return hashed, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifies a password against its hash."""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, password_hash)


def authenticate_user(
    username: str,
    password: str,
    user_store: Dict[str, User],
    salt_store: Dict[str, str],
) -> User:
    """Authenticates a user and returns the User object if successful."""
    user = user_store.get(username)
    if user is None:
        raise AuthenticationError("User not found")

    salt = salt_store.get(username)
    if salt is None:
        raise AuthenticationError("Invalid credentials")

    if not verify_password(password, user.password_hash, salt):
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        raise AuthenticationError("User account is disabled")

    return user
'''


# =============================================================================
# Evaluation Functions
# =============================================================================

def eval_token_savings(name: str, raw_content: str, tldr_output: str, min_savings: float = 0.5) -> EvalResult:
    """Evaluate token savings between raw file and tldr output."""
    raw_tokens = count_tokens(raw_content)
    tldr_tokens = count_tokens(tldr_output)

    if raw_tokens == 0:
        return EvalResult(name, False, "Raw content is empty", 0, 0, 0.0)

    savings = 1.0 - (tldr_tokens / raw_tokens)
    passed = savings >= min_savings

    return EvalResult(
        name=name,
        passed=passed,
        details=f"Raw: {raw_tokens} tokens, TLDR: {tldr_tokens} tokens, Savings: {savings:.1%}",
        raw_tokens=raw_tokens,
        tldr_tokens=tldr_tokens,
        savings_pct=savings * 100,
    )


def eval_typescript_signatures(tldr_output: str) -> EvalResult:
    """Verify TypeScript signatures use 'function' not 'def'."""
    try:
        data = json.loads(tldr_output)
    except json.JSONDecodeError:
        return EvalResult("TypeScript signatures", False, "Invalid JSON output")

    functions = data.get("functions", [])
    if not functions:
        return EvalResult("TypeScript signatures", False, "No functions found in output")

    issues = []
    for func in functions:
        sig = func.get("signature", "")
        if "def " in sig:
            issues.append(f"{func['name']}: uses 'def' instead of 'function'")
        if not ("function " in sig or sig.startswith("class ")):
            if "def " not in sig:  # Already caught above
                issues.append(f"{func['name']}: unexpected signature format: {sig}")

    if issues:
        return EvalResult("TypeScript signatures", False, "; ".join(issues[:3]))

    return EvalResult(
        "TypeScript signatures",
        True,
        f"All {len(functions)} functions use correct 'function' keyword",
    )


def eval_rust_signatures(tldr_output: str) -> EvalResult:
    """Verify Rust signatures use 'fn' not 'def'."""
    try:
        data = json.loads(tldr_output)
    except json.JSONDecodeError:
        return EvalResult("Rust signatures", False, "Invalid JSON output")

    functions = data.get("functions", [])
    if not functions:
        return EvalResult("Rust signatures", False, "No functions found in output")

    issues = []
    for func in functions:
        sig = func.get("signature", "")
        name = func.get("name", "")
        # Skip class definitions
        if sig.startswith("class "):
            continue
        if "def " in sig:
            issues.append(f"{name}: uses 'def' instead of 'fn'")
        if not ("fn " in sig or sig.startswith("class ")):
            issues.append(f"{name}: unexpected signature format: {sig}")

    if issues:
        return EvalResult("Rust signatures", False, "; ".join(issues[:3]))

    fn_count = sum(1 for f in functions if "fn " in f.get("signature", ""))
    return EvalResult(
        "Rust signatures",
        True,
        f"{fn_count} functions use correct 'fn' keyword",
    )


def eval_clean_function_names(tldr_output: str) -> EvalResult:
    """Verify function names don't have export/async prefixes."""
    try:
        data = json.loads(tldr_output)
    except json.JSONDecodeError:
        return EvalResult("Clean function names", False, "Invalid JSON output")

    functions = data.get("functions", [])
    if not functions:
        return EvalResult("Clean function names", False, "No functions found in output")

    bad_prefixes = ["export ", "async ", "default ", "pub ", "pub(crate) "]
    issues = []

    for func in functions:
        name = func.get("name", "")
        for prefix in bad_prefixes:
            if name.startswith(prefix):
                issues.append(f"'{name}' has prefix '{prefix.strip()}'")
                break

    if issues:
        return EvalResult("Clean function names", False, "; ".join(issues[:3]))

    return EvalResult(
        "Clean function names",
        True,
        f"All {len(functions)} function names are clean",
    )


def eval_structure_single_file(file_path: str, expected_lang: str) -> EvalResult:
    """Verify structure command works on single files and detects language."""
    output = run_tldrs(["structure", file_path])

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return EvalResult(
            f"Single file structure ({expected_lang})",
            False,
            f"Invalid JSON output: {output[:100]}",
        )

    detected_lang = data.get("language", "")
    files = data.get("files", [])

    if detected_lang != expected_lang:
        return EvalResult(
            f"Single file structure ({expected_lang})",
            False,
            f"Wrong language detected: {detected_lang}",
        )

    if not files:
        return EvalResult(
            f"Single file structure ({expected_lang})",
            False,
            "No files in output",
        )

    func_count = len(files[0].get("functions", []))
    return EvalResult(
        f"Single file structure ({expected_lang})",
        True,
        f"Detected {expected_lang}, found {func_count} functions",
    )


def create_compact_structure(data: dict) -> str:
    """Create a compact string representation of structure data."""
    lines = []
    for f in data.get("files", []):
        path = f.get("path", "")
        funcs = f.get("functions", [])
        classes = f.get("classes", [])
        if funcs or classes:
            lines.append(f"# {path}")
            for c in classes:
                lines.append(f"  class {c}")
            for fn in funcs:
                lines.append(f"  {fn}()")
    return "\n".join(lines)


# =============================================================================
# Main Evaluation Runner
# =============================================================================

def run_all_evals() -> list[EvalResult]:
    """Run all evaluations and return results."""
    results = []

    # Create temp files for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        ts_file = Path(tmpdir) / "test.ts"
        rs_file = Path(tmpdir) / "test.rs"
        py_file = Path(tmpdir) / "test.py"

        ts_file.write_text(TYPESCRIPT_FILE)
        rs_file.write_text(RUST_FILE)
        py_file.write_text(PYTHON_FILE)

        # Run extractions
        ts_extract = run_tldrs(["extract", str(ts_file)])
        rs_extract = run_tldrs(["extract", str(rs_file)])
        py_extract = run_tldrs(["extract", str(py_file)])

        # Run structure (codemap) - this is the token-efficient format
        ts_structure = run_tldrs(["structure", str(ts_file)])
        rs_structure = run_tldrs(["structure", str(rs_file)])
        py_structure = run_tldrs(["structure", str(py_file)])

        # Create compact representation for token comparison
        try:
            ts_compact = create_compact_structure(json.loads(ts_structure))
            rs_compact = create_compact_structure(json.loads(rs_structure))
            py_compact = create_compact_structure(json.loads(py_structure))
        except json.JSONDecodeError:
            ts_compact = rs_compact = py_compact = ""

        # Token savings evaluations - compare structure output to raw
        results.append(eval_token_savings(
            "TypeScript structure vs raw",
            TYPESCRIPT_FILE,
            ts_structure,
            min_savings=0.20,  # At least 20% savings for structure JSON
        ))

        results.append(eval_token_savings(
            "Rust structure vs raw",
            RUST_FILE,
            rs_structure,
            min_savings=0.20,
        ))

        results.append(eval_token_savings(
            "Python structure vs raw",
            PYTHON_FILE,
            py_structure,
            min_savings=0.20,
        ))

        # Compact format savings (signatures only, no implementation)
        results.append(eval_token_savings(
            "TypeScript compact vs raw",
            TYPESCRIPT_FILE,
            ts_compact,
            min_savings=0.70,  # 70%+ savings for compact format
        ))

        results.append(eval_token_savings(
            "Rust compact vs raw",
            RUST_FILE,
            rs_compact,
            min_savings=0.70,
        ))

        results.append(eval_token_savings(
            "Python compact vs raw",
            PYTHON_FILE,
            py_compact,
            min_savings=0.70,
        ))

        # Signature format evaluations
        results.append(eval_typescript_signatures(ts_extract))
        results.append(eval_rust_signatures(rs_extract))

        # Clean function name evaluations
        results.append(eval_clean_function_names(ts_extract))
        results.append(eval_clean_function_names(rs_extract))

        # Single file structure evaluations
        results.append(eval_structure_single_file(str(ts_file), "typescript"))
        results.append(eval_structure_single_file(str(rs_file), "rust"))
        results.append(eval_structure_single_file(str(py_file), "python"))

    return results


def print_results(results: list[EvalResult]) -> bool:
    """Print evaluation results and return True if all passed."""
    print("=" * 70)
    print("tldr-swinton Token Efficiency Evaluation")
    print("=" * 70)
    print()

    passed_count = 0
    failed_count = 0

    # Group by category
    structure_savings = [r for r in results if "structure vs raw" in r.name.lower()]
    compact_savings = [r for r in results if "compact vs raw" in r.name.lower()]
    signature_results = [r for r in results if "signature" in r.name.lower()]
    name_results = [r for r in results if "name" in r.name.lower()]
    structure_results = [r for r in results if "single file structure" in r.name.lower()]

    def print_section(title: str, section_results: list[EvalResult]):
        nonlocal passed_count, failed_count
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

    print_section("Structure JSON Token Savings (target: ≥20%)", structure_savings)
    print_section("Compact Format Token Savings (target: ≥70%)", compact_savings)
    print_section("Signature Formats", signature_results)
    print_section("Function Name Cleaning", name_results)
    print_section("Single File Support", structure_results)

    # Summary
    total = passed_count + failed_count
    print("=" * 70)
    print(f"SUMMARY: {passed_count}/{total} evaluations passed")

    if compact_savings:
        avg_compact_savings = sum(r.savings_pct for r in compact_savings) / len(compact_savings)
        print(f"Average compact format savings: {avg_compact_savings:.1f}%")

    if structure_savings:
        avg_structure_savings = sum(r.savings_pct for r in structure_savings) / len(structure_savings)
        print(f"Average structure JSON savings: {avg_structure_savings:.1f}%")

    print("=" * 70)

    return failed_count == 0


if __name__ == "__main__":
    results = run_all_evals()
    all_passed = print_results(results)
    sys.exit(0 if all_passed else 1)
