# LLM Workflow Quick Reference

## 🚀 Quick Start

### 1. **Environment Setup**
```bash
# Set OpenAI API key (required for enhanced LLM research)
export OPENAI_API_KEY="your-openai-api-key-here"

# Optional: Set specific model
export OPENAI_MODEL_RESOLVER="gpt-5"
```

### 2. **Test Enhanced LLM Workflow**
```bash
# Test single trial with LLM research
cd ncfd
source .venv/bin/activate
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT06467357 --decider llm

# Test batch processing
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --limit 3 --decider llm
```

## 📋 Common Commands

### **Single Trial Resolution**
```bash
# Enhanced LLM research (recommended)
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct <NCT_ID> --decider llm

# Deterministic only (fastest)
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct <NCT_ID> --decider det

# Probabilistic only (ML-based)
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct <NCT_ID> --decider prob

# Auto-decider (deterministic → probabilistic → LLM)
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct <NCT_ID>
```

### **Batch Processing**
```bash
# Process multiple trials with LLM research
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --limit <N> --decider llm

# Process with persistence to database
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --limit <N> --decider llm --persist

# Process with trial updates
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --limit <N> --decider llm --persist --apply-trial
```

### **Makefile Usage** (from project root)
```bash
# Setup environment
make setup
make reup

# Single trial
make resolve-nct SPONSOR="Company Name" NCT="NCT_ID"

# Batch processing
make resolve-batch LIMIT=10
```

## 🔍 Monitoring & Health Checks

### **Quick Health Check**
```bash
# System health check
echo "=== System Health Check ==="
echo "1. Database:" && psql "$PSQL_DSN" -c "SELECT version();" 2>/dev/null && echo "✅ OK" || echo "❌ Failed"
echo "2. CT.gov API:" && curl -s "https://clinicaltrials.gov/api/v2/studies/NCT06467357" >/dev/null && echo "✅ OK" || echo "❌ Failed"
echo "3. OpenAI key:" && [ -n "$OPENAI_API_KEY" ] && echo "✅ Set" || echo "❌ Missing"
```

### **Database Monitoring**
```bash
# LLM resolution counts (last 24h)
psql "$PSQL_DSN" -c "
SELECT 
    decided_by,
    COUNT(*) as total,
    COUNT(CASE WHEN mode = 'accept' THEN 1 END) as accepts,
    ROUND(100.0 * COUNT(CASE WHEN mode = 'accept' THEN 1 END) / COUNT(*), 1) as success_rate
FROM resolver_decisions 
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY decided_by;"

# Recent LLM decisions
psql "$PSQL_DSN" -c "
SELECT nct_id, mode, company_id, confidence, created_at
FROM resolver_decisions 
WHERE decided_by = 'llm'
ORDER BY created_at DESC
LIMIT 10;"
```

## 🛠️ Troubleshooting

### **Common Issues & Solutions**

#### 1. **No Sponsor Information Returned**
```bash
# Test ClinicalTrials.gov API directly
curl "https://clinicaltrials.gov/api/v2/studies/NCT06467357" | jq '.protocolSection.sponsorCollaboratorsModule.leadSponsor'
```

#### 2. **LLM Calls Failing**
```bash
# Check OpenAI API key
echo $OPENAI_API_KEY

# Test OpenAI connection
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-5","messages":[{"role":"user","content":"test"}]}' \
     https://api.openai.com/v1/chat/completions
```

#### 3. **Low Confidence Matches**
```bash
# Check company database
psql "$PSQL_DSN" -c "SELECT COUNT(*) FROM companies;"

# Test fuzzy matching
psql "$PSQL_DSN" -c "
SELECT name, similarity(LOWER(name), 'astrazeneca') as sim
FROM companies 
WHERE LOWER(name) % 'astrazeneca'
ORDER BY sim DESC LIMIT 5;"
```

### **Debug Commands**
```bash
# Test enhanced LLM workflow
cd ncfd && source .venv/bin/activate
PYTHONPATH=src python -c "
from ncfd.mapping.llm_decider import decide_with_llm_research
decision, raw = decide_with_llm_research(
    run_id='test-123',
    nct_id='NCT06467357',
    session=None,
    context={'domains': [], 'drug_code_hit': False}
)
print(f'Mode: {decision.mode}, Company: {decision.company_name}, Confidence: {decision.confidence}')
"

# Check research evidence
psql "$PSQL_DSN" -c "
SELECT nct_id, research_evidence->>'trial_metadata' as trial_meta
FROM resolver_decisions 
WHERE research_evidence IS NOT NULL
LIMIT 3;"
```

## 📊 Performance Metrics

### **Resolution Success Rates**
```bash
# Success rates by method (last 7 days)
psql "$PSQL_DSN" -c "
SELECT 
    decided_by,
    ROUND(100.0 * COUNT(CASE WHEN mode = 'accept' THEN 1 END) / COUNT(*), 2) as success_rate,
    COUNT(*) as total_decisions
FROM resolver_decisions 
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY decided_by
ORDER BY success_rate DESC;"
```

### **API Usage Patterns**
```bash
# Hourly decision counts (last 7 days)
psql "$PSQL_DSN" -c "
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    decided_by,
    COUNT(*) as decisions
FROM resolver_decisions 
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY hour, decided_by
ORDER BY hour DESC;"
```

## 🎯 Production Workflows

### **High-Accuracy Production**
```bash
# Process unresolved trials with LLM research
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch \
  --limit 100 \
  --decider llm \
  --persist \
  --apply-trial
```

### **Training Data Generation**
```bash
# Generate features and decisions for model improvement
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch \
  --limit 500 \
  --decider llm \
  --persist
```

### **Quality Assurance**
```bash
# Process trials and route uncertain cases to review
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch \
  --limit 50 \
  --decider llm \
  --persist
```

## 📝 Output Examples

### **Standard Output**
```
                       Deterministic Resolution                       
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Method                ┃ Company ID ┃ Evidence                      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ det_exact:alias_exact │      10092 │ alias_norm=astrazeneca       │
└───────────────────────┴────────────┴───────────────────────────────┘
─────────────────────────────────────────────── Decision ────────────────────────────────────────────────
mode: deterministic:accept | leader company_id: 10092 | p: 1.0000 | margin: 1.0000
```

### **LLM Research Output**
```
NCT06467357: Probabilistic didn't accept, trying LLM Research...
NCT06467357 :: 'AstraZeneca' -> LLM accept (cid=12345, conf=0.90)
```

### **JSON Output** (for programmatic use)
```bash
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT06467357 --decider llm --json
```

## 🔗 Related Documentation

- **Full Implementation Guide**: `docs/llm_workflow_upgrade_implementation.md`
- **Design Plan**: `docs/llm_workflow_upgrade_plan.md`
- **Problem 1 Solution**: `docs/problem1_implementation_guide.md`

## 💡 Tips & Best Practices

1. **Start Small**: Test with a few trials before processing large batches
2. **Monitor Costs**: Track OpenAI API usage and costs
3. **Use Persistence**: Always use `--persist` in production to save training data
4. **Health Checks**: Run health checks before large batch processing
5. **Fallback Strategy**: The system automatically falls back to human review when needed
6. **Training Loop**: LLM decisions contribute to probabilistic model improvement

## 🆘 Need Help?

If you encounter issues:

1. **Check the health check commands above**
2. **Review the troubleshooting section**
3. **Check the full implementation guide**
4. **Verify environment variables are set correctly**
5. **Ensure database connectivity**
6. **Monitor API rate limits**
