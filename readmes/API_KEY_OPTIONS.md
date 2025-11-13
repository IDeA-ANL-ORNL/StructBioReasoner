# API Key Options for Integration Tests

## ✅ YES! You can use EITHER Anthropic OR OpenAI

The integration test (`test_jnana_structbioreasoner_integration.py`) has been updated to **automatically detect** which API key you have set and use the appropriate LLM.

---

## 🔑 How to Use

### Option 1: Anthropic (Claude)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python test_jnana_structbioreasoner_integration.py
```

### Option 2: OpenAI (GPT-4)

```bash
export OPENAI_API_KEY="sk-..."
python test_jnana_structbioreasoner_integration.py
```

---

## 🤖 How It Works

The test automatically detects which API key is available:

1. **If only `OPENAI_API_KEY` is set** → Uses OpenAI
2. **If only `ANTHROPIC_API_KEY` is set** → Uses Anthropic
3. **If both are set** → Uses Anthropic (takes precedence)
4. **If neither is set** → Shows warning and may fail

---

## 📝 What Changed

### Before (Anthropic only):
```python
coscientist = CoScientist(llm_config="anthropic")
```

### After (Auto-detect):
```python
# Determine which LLM to use based on environment variables
llm_config = "anthropic"  # default
if os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
    llm_config = "openai"
    logger.info("Using OpenAI (detected OPENAI_API_KEY)")
elif os.getenv("ANTHROPIC_API_KEY"):
    llm_config = "anthropic"
    logger.info("Using Anthropic (detected ANTHROPIC_API_KEY)")

coscientist = CoScientist(llm_config=llm_config)
```

---

## 🧪 Test Examples

### Example 1: Using OpenAI

```bash
# Set OpenAI key
export OPENAI_API_KEY="sk-proj-..."

# Run quick test (no API key needed)
python test_quick_integration.py

# Run full test (uses OpenAI)
python test_jnana_structbioreasoner_integration.py
```

**Expected output:**
```
2025-11-10 10:30:45 - __main__ - INFO - Using OpenAI (detected OPENAI_API_KEY)
2025-11-10 10:30:45 - __main__ - INFO - Initializing CoScientist with openai...
```

---

### Example 2: Using Anthropic

```bash
# Set Anthropic key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run quick test (no API key needed)
python test_quick_integration.py

# Run full test (uses Anthropic)
python test_jnana_structbioreasoner_integration.py
```

**Expected output:**
```
2025-11-10 10:30:45 - __main__ - INFO - Using Anthropic (detected ANTHROPIC_API_KEY)
2025-11-10 10:30:45 - __main__ - INFO - Initializing CoScientist with anthropic...
```

---

### Example 3: Both Keys Set

```bash
# Set both keys
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-proj-..."

# Run test (uses Anthropic by default)
python test_jnana_structbioreasoner_integration.py
```

**Expected output:**
```
2025-11-10 10:30:45 - __main__ - INFO - Using Anthropic (detected ANTHROPIC_API_KEY)
2025-11-10 10:30:45 - __main__ - INFO - Initializing CoScientist with anthropic...
```

---

## 🔍 Verification

You can verify which LLM is being used by checking the log output:

```bash
python test_jnana_structbioreasoner_integration.py 2>&1 | grep "Using"
```

**Output examples:**
- `Using OpenAI (detected OPENAI_API_KEY)`
- `Using Anthropic (detected ANTHROPIC_API_KEY)`

---

## ⚠️ Troubleshooting

### No API Key Set

**Problem:**
```
WARNING - No API key detected. Set ANTHROPIC_API_KEY or OPENAI_API_KEY
```

**Solution:**
```bash
# Set at least one API key
export ANTHROPIC_API_KEY="sk-ant-..."
# OR
export OPENAI_API_KEY="sk-..."
```

---

### Wrong API Key Format

**Problem:**
```
AuthenticationError: Invalid API key
```

**Solution:**
- **Anthropic keys** start with `sk-ant-`
- **OpenAI keys** start with `sk-` or `sk-proj-`
- Make sure you copied the full key without extra spaces

---

### API Rate Limits

**Problem:**
```
RateLimitError: Rate limit exceeded
```

**Solution:**
- Wait a few minutes and try again
- Use a different API key
- Switch to the other provider (Anthropic ↔ OpenAI)

---

## 💰 Cost Considerations

### Anthropic (Claude)
- **Model:** Claude 3.5 Sonnet (default in Jnana)
- **Cost:** ~$3 per million input tokens, ~$15 per million output tokens
- **Test cost:** ~$0.01-0.05 per full test run

### OpenAI (GPT-4)
- **Model:** GPT-4 Turbo (default in Jnana)
- **Cost:** ~$10 per million input tokens, ~$30 per million output tokens
- **Test cost:** ~$0.05-0.15 per full test run

**Note:** Quick test (`test_quick_integration.py`) is FREE - no API calls!

---

## 📚 Related Files

All these files have been updated to support both API keys:

- ✅ `test_jnana_structbioreasoner_integration.py` - Main integration test
- ✅ `README_TESTING.md` - Quick start guide
- ✅ `ANSWER_TO_YOUR_QUESTION.md` - Direct answer document
- ✅ `API_KEY_OPTIONS.md` - This file

---

## 🎯 Summary

**Question:** Is there a test that requires OpenAI key, not Anthropic key?

**Answer:** **YES!** The same test (`test_jnana_structbioreasoner_integration.py`) now supports BOTH:

```bash
# Use OpenAI
export OPENAI_API_KEY="sk-..."
python test_jnana_structbioreasoner_integration.py

# OR use Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
python test_jnana_structbioreasoner_integration.py
```

**The test automatically detects which key you have and uses the appropriate LLM!** 🎉

---

## 🚀 Quick Start

```bash
# Step 1: Set your API key (choose one)
export OPENAI_API_KEY="sk-..."        # Option 1
# OR
export ANTHROPIC_API_KEY="sk-ant-..."  # Option 2

# Step 2: Run quick test (no API key needed)
python test_quick_integration.py

# Step 3: Run full test (uses your API key)
python test_jnana_structbioreasoner_integration.py
```

**That's it! The test will automatically use whichever API key you set.** ✨

