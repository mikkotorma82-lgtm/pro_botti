# Fix Summary: 429 Rate Limit Errors and Training Configuration

## Problem Statement
The bot was experiencing 429 (Too Many Requests) rate limit errors from the Capital.com API due to:
1. Multiple login attempts - each CapitalClient instance created a new session
2. Excessive historical data fetching - attempting to fetch 10 years of data for training

## Solutions Implemented

### 1. Session Reuse in CapitalClient

**Implementation:**
- Added module-level session cache (`_SHARED_SESSION`)
- Implemented TTL (Time-To-Live) mechanism (default: 540 seconds / 9 minutes)
- Added thread safety with `threading.Lock`
- Error handling that clears cached session on authentication failure

**Key Files Changed:**
- `tools/capital_client.py`: Added session reuse logic
- `tests/test_capital_client.py`: Comprehensive test coverage

**Benefits:**
- Reduces login attempts from N (one per instance) to 1 per TTL period
- Prevents 429 errors during normal operation
- Thread-safe for concurrent usage
- Backward compatible - no changes needed to existing code

### 2. Reduced Training History

**Implementation:**
- Updated `history/history_utils.py` DEFAULT_TARGET_DAYS configuration
- Standardized all timeframes to 3 years (1095 days)

**Changes:**
| Timeframe | Before | After | Reduction |
|-----------|--------|-------|-----------|
| 15m       | 730 days (2 years) | 1095 days (3 years) | Increased for consistency |
| 1h        | 1460 days (4 years) | 1095 days (3 years) | -365 days |
| 4h        | 3650 days (10 years) | 1095 days (3 years) | -2555 days ⭐ |

**Benefits:**
- Dramatically reduces API calls for 4h timeframe training
- Faster data fetching and training initialization
- 3 years is still sufficient for robust model training
- Consistent history period across all timeframes

### 3. GOLD and Macros Support

**Status:** Already supported, enhanced by session reuse

**Configuration:**
- XAUUSD (GOLD) is in the SYMBOLS list in `botti.env`
- Macro indicators (DXY, SPX, VIX) supported via `macro_epics` parameter in gold_features_capital.py
- Session reuse benefits all data fetching including GOLD and macro indicators

## Testing

### Test Coverage
- 10 comprehensive tests covering:
  - Session reuse across instances
  - Session expiration after TTL
  - Thread safety with concurrent access
  - Authentication failure handling
  - All existing functionality
- All tests pass successfully

### Security Scan
- CodeQL analysis: 0 alerts (clean)
- No security vulnerabilities introduced

## Configuration

### Environment Variables
```bash
# Session TTL (optional, defaults to 540 seconds)
export CAPITAL_LOGIN_TTL=540
```

### Training History
Training history is now automatically configured to 3 years for all timeframes via `history/history_utils.py`.

## Impact Assessment

### Before:
```
Bot initialization:
- 10+ CapitalClient instances created
- 10+ login attempts
- 429 errors likely
- Data fetch: 10 years (3650 days) for 4h timeframe
- Multiple 429 errors during data fetch
```

### After:
```
Bot initialization:
- 10+ CapitalClient instances created
- 1 login attempt (session reused)
- No 429 errors from login
- Data fetch: 3 years (1095 days) for all timeframes
- Significantly reduced API load
- Faster initialization
```

### Estimated API Call Reduction
- Login calls: ~90% reduction (from N to 1 per 9 minutes)
- Historical data calls for 4h: ~70% reduction (from 10 years to 3 years)
- Total: Significant reduction in 429 error probability

## Migration Notes

### Backward Compatibility
- ✅ No breaking changes
- ✅ Existing code works without modifications
- ✅ Environment variable is optional

### Rollback Plan
If issues arise:
1. Revert `tools/capital_client.py` to remove session caching
2. Revert `history/history_utils.py` to previous values
3. No database or configuration changes needed

## Recommendations for Production

1. **Monitor session reuse:**
   - Check logs for "Reusing existing Capital.com session" messages
   - Should see mostly session reuse, not "Creating new Capital.com session"

2. **Adjust TTL if needed:**
   - Default 540s (9 minutes) is conservative
   - Can increase to 600s+ if Capital.com tokens last longer
   - Can decrease if experiencing auth errors

3. **Monitor training data quality:**
   - 3 years should be sufficient for most models
   - If model quality degrades, can increase via code change
   - Consider model performance metrics

4. **GOLD and macros:**
   - Ensure macro_epics are configured if using GOLD trading
   - Example: `{"DXY": "US_DOLLAR_INDEX", "SPX": "US500", "VIX": "VIX_INDEX"}`

## Files Changed

1. `tools/capital_client.py` - Session reuse implementation
2. `tests/test_capital_client.py` - Comprehensive tests
3. `history/history_utils.py` - Training history configuration
4. `docs/session_reuse.md` - Documentation

## Success Criteria

- ✅ All tests pass (10/10)
- ✅ No security vulnerabilities (CodeQL clean)
- ✅ Code review feedback addressed
- ✅ Documentation complete
- ✅ Backward compatible

## Conclusion

This fix addresses the root causes of 429 rate limit errors:
1. **Session reuse** prevents excessive login attempts
2. **Reduced training history** prevents excessive data fetching
3. **Thread safety** ensures reliable operation under concurrent load

The implementation is production-ready, well-tested, and backward compatible.
