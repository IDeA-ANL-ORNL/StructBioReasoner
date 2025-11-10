# Quick Install: Jnana as a Package

## 🚀 TL;DR

```bash
# Install Jnana
cd ~/Desktop/Code/Jnana
pip install -e .

# Verify
python -c "from jnana.protognosis.core.coscientist import CoScientist; print('✅ Works!')"

# Run your tests
cd ~/Desktop/Code/StructBioReasoner
python test_quick_integration.py
```

---

## 📦 Installation Commands

### Basic Install (Recommended)
```bash
cd ~/Desktop/Code/Jnana
pip install -e .
```

### With Development Tools
```bash
cd ~/Desktop/Code/Jnana
pip install -e ".[dev]"
```

### With Everything
```bash
cd ~/Desktop/Code/Jnana
pip install -e ".[all]"
```

---

## ✅ Verify Installation

```bash
# Check package
pip show jnana

# Test import
python -c "import jnana; print(jnana.__version__)"

# Test CoScientist
python -c "from jnana.protognosis.core.coscientist import CoScientist; print('✅')"
```

---

## 🔧 Update Your Test Files

### Remove This Line

In all your test files, **DELETE** this:

```python
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))  # ❌ DELETE THIS
```

### Files to Update

- `test_quick_integration.py`
- `test_jnana_structbioreasoner_integration.py`
- `example_full_pipeline.py`

---

## 🎯 What Changed

### Before
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / '../Jnana'))

from jnana.protognosis.core.coscientist import CoScientist
```

### After
```python
from jnana.protognosis.core.coscientist import CoScientist  # Clean!
```

---

## 📚 Files Created

1. **`../Jnana/pyproject.toml`** - Package configuration
2. **`../Jnana/INSTALL.md`** - Full installation guide
3. **`JNANA_PACKAGE_SETUP.md`** - Detailed summary
4. **`QUICK_INSTALL_JNANA.md`** - This file

---

## 🐛 Troubleshooting

### "No module named 'jnana'"
```bash
cd ~/Desktop/Code/Jnana
pip install -e .
```

### Dependency conflicts
```bash
python -m venv venv_clean
source venv_clean/bin/activate
pip install -e ~/Desktop/Code/Jnana
```

---

## ✨ Benefits

- ✅ Clean imports everywhere
- ✅ No manual path management
- ✅ Changes immediately available (editable mode)
- ✅ Works from any directory
- ✅ Professional package structure

---

**Install now and enjoy clean imports! 🎉**

