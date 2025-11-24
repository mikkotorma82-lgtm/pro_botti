# Session Reuse Implementation for CapitalClient

## Problem
The bot was experiencing 429 (Too Many Requests) rate limit errors from the Capital.com API. This was caused by creating multiple `CapitalClient` instances throughout the codebase, where each instance would perform a separate login operation.

## Solution
Implemented a session reuse pattern using module-level caching in `tools/capital_client.py`. The implementation includes:

1. **Module-level session cache**: Shared across all `CapitalClient` instances
2. **TTL (Time-to-Live) management**: Sessions expire after a configurable period (default: 540 seconds / 9 minutes)
3. **Automatic session refresh**: New sessions are created when the cached session expires

## Key Changes

### Code Changes
- Added module-level variables `_SHARED_SESSION`, `_SESSION_LAST_LOGIN`, and `_SESSION_TTL`
- Introduced `_get_or_create_session()` method that checks session validity before creating new ones
- Modified `_authenticate()` to accept a session parameter instead of using `self.session`
- Added informative logging to track session reuse and creation

### Test Changes
- Updated all existing tests to use `_get_or_create_session` mock instead of `_authenticate`
- Added `test_session_reuse_across_instances()` to verify session sharing
- Added `test_session_refresh_after_ttl()` to verify session expiration and refresh

## Configuration

The session TTL can be configured via environment variable:
```bash
export CAPITAL_LOGIN_TTL=540  # Default: 540 seconds (9 minutes)
```

## Benefits

1. **Reduced API calls**: Multiple `CapitalClient` instances created within the TTL period share the same session
2. **Prevents 429 errors**: Dramatically reduces login attempts to the Capital.com API
3. **Backward compatible**: No changes needed to existing code that uses `CapitalClient`
4. **Automatic management**: Session refresh happens automatically when TTL expires

## Example

Before the fix:
```python
client1 = CapitalClient()  # Login #1
client2 = CapitalClient()  # Login #2
client3 = CapitalClient()  # Login #3
# Result: 3 login attempts, potential 429 errors
```

After the fix:
```python
client1 = CapitalClient()  # Login #1, session cached
client2 = CapitalClient()  # Reuses session from client1
client3 = CapitalClient()  # Reuses session from client1
# Result: 1 login attempt, no 429 errors
```

## Testing

Run the test suite to verify the implementation:
```bash
python tests/test_capital_client.py
```

All tests should pass, including the new session reuse tests.
