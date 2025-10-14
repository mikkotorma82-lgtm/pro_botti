#!/usr/bin/env bash
# Auto-retrain pipeline: backfill → train → evaluate → select-top
# This script automates the full trading bot update cycle

set -euo pipefail

# Configuration
ROOT="${ROOT:-/home/runner/work/pro_botti/pro_botti}"
cd "$ROOT"

# Load environment if exists
if [ -f botti.env ]; then
    source botti.env
fi

# Activate venv if exists
if [ -d venv ]; then
    source venv/bin/activate
fi

# Get symbols and timeframes from config or env
SYMBOLS="${SYMBOLS:-EURUSD,GBPUSD,US500,US100,BTCUSDT,ETHUSDT}"
TFS="${TFS:-15m,1h,4h}"
TOP_K="${TOP_K:-5}"
MIN_TRADES="${MIN_TRADES:-25}"
EVAL_LOOKBACK_DAYS="${EVAL_LOOKBACK_DAYS:-365}"

# Parse into arrays
IFS=',' read -ra SYMS <<< "$SYMBOLS"
IFS=',' read -ra TF_ARR <<< "$TFS"

echo "=========================================="
echo "AUTO RETRAIN PIPELINE"
echo "=========================================="
echo "Start time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Symbols: ${SYMS[*]}"
echo "Timeframes: ${TF_ARR[*]}"
echo "Top-K: $TOP_K"
echo "Min trades: $MIN_TRADES"
echo ""

# Step 1: Backfill data
echo "=========================================="
echo "STEP 1: BACKFILL DATA"
echo "=========================================="

BACKFILL_ERRORS=0
for sym in "${SYMS[@]}"; do
    sym="${sym//[[:space:]]/}"
    [ -z "$sym" ] && continue
    
    for tf in "${TF_ARR[@]}"; do
        tf="${tf//[[:space:]]/}"
        [ -z "$tf" ] && continue
        
        # Determine years based on timeframe
        case "$tf" in
            15m) YEARS=2 ;;
            1h)  YEARS=4 ;;
            4h)  YEARS=10 ;;
            *)   YEARS=5 ;;
        esac
        
        echo "Backfilling $sym $tf ($YEARS years)..."
        
        if python3 tools/backfill.py "$sym" "$tf" "$YEARS" 2>&1 | tee -a logs/backfill.log; then
            echo "✓ $sym $tf backfilled"
        else
            echo "✗ $sym $tf backfill failed"
            ((BACKFILL_ERRORS++))
        fi
    done
done

echo ""
echo "Backfill complete. Errors: $BACKFILL_ERRORS"
echo ""

# Step 2: Train models
echo "=========================================="
echo "STEP 2: TRAIN MODELS"
echo "=========================================="

# Use existing trainer if available
if [ -f tools/trainer_daemon.py ]; then
    # Run one-shot training
    TRAIN_ERRORS=0
    for sym in "${SYMS[@]}"; do
        sym="${sym//[[:space:]]/}"
        [ -z "$sym" ] && continue
        
        for tf in "${TF_ARR[@]}"; do
            tf="${tf//[[:space:]]/}"
            [ -z "$tf" ] && continue
            
            echo "Training $sym $tf..."
            
            # Call training function - adapt based on existing trainer
            if python3 -c "
import sys, os
sys.path.insert(0, '.')
from tools.trainer_daemon import train_one
result = train_one('$sym', '$tf')
print(f\"Trained {result['symbol']}_{result['tf']}: pf={result.get('pf', 0):.2f} wr={result.get('win_rate', 0)*100:.1f}%\")
" 2>&1 | tee -a logs/train.log; then
                echo "✓ $sym $tf trained"
            else
                echo "✗ $sym $tf training failed"
                ((TRAIN_ERRORS++))
            fi
        done
    done
    
    echo ""
    echo "Training complete. Errors: $TRAIN_ERRORS"
    echo ""
else
    echo "Warning: trainer_daemon.py not found, skipping training"
    echo "Models will be used as-is"
    echo ""
fi

# Step 3: Evaluate models
echo "=========================================="
echo "STEP 3: EVALUATE MODELS"
echo "=========================================="

mkdir -p results/metrics

EVAL_ERRORS=0
for tf in "${TF_ARR[@]}"; do
    tf="${tf//[[:space:]]/}"
    [ -z "$tf" ] && continue
    
    echo "Evaluating timeframe: $tf"
    
    if python3 scripts/evaluate.py \
        --symbols "${SYMS[@]}" \
        --timeframes "$tf" \
        --lookback-days "$EVAL_LOOKBACK_DAYS" \
        2>&1 | tee -a logs/evaluate.log; then
        echo "✓ Evaluation complete for $tf"
    else
        echo "✗ Evaluation failed for $tf"
        ((EVAL_ERRORS++))
    fi
done

echo ""
echo "Evaluation complete. Errors: $EVAL_ERRORS"
echo ""

# Step 4: Select top symbols
echo "=========================================="
echo "STEP 4: SELECT TOP SYMBOLS"
echo "=========================================="

# Parse weights from env if provided
WEIGHTS_ARG=""
if [ -n "${SELECT_WEIGHTS:-}" ]; then
    WEIGHTS_ARG="--weights '$SELECT_WEIGHTS'"
fi

SELECT_ERRORS=0
for tf in "${TF_ARR[@]}"; do
    tf="${tf//[[:space:]]/}"
    [ -z "$tf" ] && continue
    
    echo "Selecting top-$TOP_K symbols for $tf..."
    
    if eval python3 -m cli select-top \
        --tf "$tf" \
        --top-k "$TOP_K" \
        --min-trades "$MIN_TRADES" \
        --lookback-days "$EVAL_LOOKBACK_DAYS" \
        $WEIGHTS_ARG \
        2>&1 | tee -a logs/select.log; then
        echo "✓ Selection complete for $tf"
        
        # Show selected symbols
        echo ""
        echo "Selected symbols for $tf:"
        python3 -m cli show-active 2>/dev/null || echo "(unable to display)"
        echo ""
    else
        echo "✗ Selection failed for $tf"
        ((SELECT_ERRORS++))
    fi
done

echo ""
echo "Selection complete. Errors: $SELECT_ERRORS"
echo ""

# Summary
echo "=========================================="
echo "PIPELINE COMPLETE"
echo "=========================================="
echo "End time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""
echo "Summary:"
echo "  Backfill errors: $BACKFILL_ERRORS"
echo "  Training errors: ${TRAIN_ERRORS:-N/A}"
echo "  Evaluation errors: $EVAL_ERRORS"
echo "  Selection errors: $SELECT_ERRORS"
echo ""

TOTAL_ERRORS=$((BACKFILL_ERRORS + ${TRAIN_ERRORS:-0} + EVAL_ERRORS + SELECT_ERRORS))

if [ $TOTAL_ERRORS -eq 0 ]; then
    echo "✓ All steps completed successfully!"
    
    # Display final selection
    echo ""
    echo "Current active symbols:"
    python3 -m cli show-active 2>/dev/null || echo "(unable to display)"
    
    exit 0
else
    echo "⚠ Pipeline completed with $TOTAL_ERRORS errors"
    echo "Check logs for details:"
    echo "  - logs/backfill.log"
    echo "  - logs/train.log"
    echo "  - logs/evaluate.log"
    echo "  - logs/select.log"
    exit 1
fi
