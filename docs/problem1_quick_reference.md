# Problem 1 Solution - Quick Reference

## 🎯 **What Was Fixed**

- **Before**: LLM bypassed deterministic/probabilistic resolvers
- **After**: Proper cascade: Deterministic → Probabilistic → LLM (only if needed)
- **Training**: All decisions now generate training data

## 🚀 **Quick Commands**

### Test the Cascade
```bash
# Activate environment
cd ncfd && source .venv/bin/activate && make reup

# Test deterministic path
PYTHONPATH=src .venv/bin/python -m ncfd.mapping.cli resolve-nct NCT02200757 --persist

# Test probabilistic path  
PYTHONPATH=src .venv/bin/python -m ncfd.mapping.cli resolve-nct NCT06467357 --persist

# Test LLM path
PYTHONPATH=src .venv/bin/python -m ncfd.mapping.cli resolve-nct NCT06467357 --persist --decider llm
```

### Production Usage
```bash
# Auto mode (recommended)
PYTHONPATH=src .venv/bin/python -m ncfd.mapping.cli resolve-batch --limit 100 --persist --apply-trial

# LLM mode
PYTHONPATH=src .venv/bin/python -m ncfd.mapping.cli resolve-batch --limit 100 --persist --apply-trial --decider llm
```

## 📊 **Database Verification**

```sql
-- Check counts
SELECT 'decisions' as table, COUNT(*) FROM resolver_decisions
UNION ALL SELECT 'features', COUNT(*) FROM resolver_features
UNION ALL SELECT 'queue', COUNT(*) FROM review_queue;

-- Check specific trial
SELECT nct_id, decided_by, match_type, company_id 
FROM resolver_decisions WHERE nct_id = 'NCT06467357';
```

## ⚙️ **Configuration**

**File**: `config/resolver.yaml`
```yaml
thresholds:
  tau_accept: 0.90        # Score for auto-accept
  review_low: 0.60        # Minimum for review
  min_top2_margin: 0.05   # Margin between top 2
```

**Environment**: `.env`
```bash
RESOLVER_DISABLE_PROB=0    # Enable probabilistic
OPENAI_API_KEY=your_key    # For LLM
```

## 🔍 **Troubleshooting**

- **Probabilistic disabled**: Check `.env` for `RESOLVER_DISABLE_PROB=1`
- **LLM not working**: Check `OPENAI_API_KEY`
- **DB issues**: Run `make db.health` and `make migrate_up`

## 📈 **Expected Results**

- **Deterministic**: Exact matches → immediate accept
- **Probabilistic**: High confidence (≥0.90) → accept, moderate (0.60-0.90) → review
- **LLM**: Used only when probabilistic uncertain
- **Training**: Every trial generates features + decisions

## 🎉 **Success Indicators**

✅ Cascade follows: Det → Prob → LLM (if needed)  
✅ Database counts increase with each run  
✅ All decision types generate training data  
✅ No errors in resolution flow  
✅ Backward compatibility maintained  

---

**Full Documentation**: See `docs/problem1_implementation_guide.md`
