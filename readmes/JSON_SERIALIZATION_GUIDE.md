# JSON Serialization for LLM Prompts - Guide

## Overview

When passing JSON objects into LLM prompts, you should serialize them to strings using `json.dumps()` for better readability and to avoid issues with nested data structures.

## Why Serialize JSON?

### ❌ Without Serialization (Direct f-string)
```python
data = {"key": "value", "nested": {"a": 1, "b": 2}}

prompt = f"""
Here is the data:
{data}
"""
# Output: "Here is the data:\n{'key': 'value', 'nested': {'a': 1, 'b': 2}}"
# Issues: Python dict repr, single quotes, not valid JSON
```

### ✅ With Serialization (json.dumps)
```python
import json

data = {"key": "value", "nested": {"a": 1, "b": 2}}
data_str = json.dumps(data, indent=2)

prompt = f"""
Here is the data:
{data_str}
"""
# Output: 
# Here is the data:
# {
#   "key": "value",
#   "nested": {
#     "a": 1,
#     "b": 2
#   }
# }
# Benefits: Valid JSON, double quotes, formatted, readable
```

## JSON Serialization Methods

### 1. Basic Serialization
```python
import json

data = {"name": "protein", "id": 123}
json_string = json.dumps(data)
# Output: '{"name": "protein", "id": 123}'
```

### 2. Pretty-Printed (Recommended for LLM Prompts)
```python
json_string = json.dumps(data, indent=2)
# Output:
# {
#   "name": "protein",
#   "id": 123
# }
```

### 3. Compact (No Whitespace)
```python
json_string = json.dumps(data, separators=(',', ':'))
# Output: '{"name":"protein","id":123}'
```

### 4. Handle Non-Serializable Types
```python
from datetime import datetime
from pathlib import Path

data = {
    "timestamp": datetime.now(),
    "path": Path("/some/path"),
    "value": 123
}

# Use default=str to convert non-serializable objects to strings
json_string = json.dumps(data, indent=2, default=str)
# Output:
# {
#   "timestamp": "2025-12-09 10:30:00.123456",
#   "path": "/some/path",
#   "value": 123
# }
```

### 5. Sort Keys (Consistent Output)
```python
json_string = json.dumps(data, indent=2, sort_keys=True)
# Keys will be alphabetically sorted
```

## Modified CHAIPromptManager Example

### Before (Direct Embedding)
```python
def running_prompt(self):
    prompt = f"""
    Output from hiperrag:
    {self.input_json}
    
    Expected format:
    {config_master['chai']}
    """
    return prompt
```

### After (JSON Serialization)
```python
def running_prompt(self):
    # Serialize input_json to a formatted string
    input_json_str = json.dumps(self.input_json, indent=2, default=str)
    config_str = json.dumps(config_master['chai'], indent=2)
    
    prompt = f"""
    Output from hiperrag:
    {input_json_str}
    
    Expected format:
    {config_str}
    """
    return prompt
```

## Best Practices

### 1. Always Use `indent=2` for LLM Prompts
```python
# ✅ Good - Easy for LLM to read
json_str = json.dumps(data, indent=2)

# ❌ Bad - Hard to read
json_str = json.dumps(data)
```

### 2. Use `default=str` for Complex Objects
```python
# ✅ Good - Handles datetime, Path, custom objects
json_str = json.dumps(data, indent=2, default=str)

# ❌ Bad - Will raise TypeError for non-serializable objects
json_str = json.dumps(data, indent=2)
```

### 3. Serialize Both Input and Config
```python
# ✅ Good - Both are properly formatted
input_str = json.dumps(input_data, indent=2, default=str)
config_str = json.dumps(config_schema, indent=2)

prompt = f"""
Input: {input_str}
Expected format: {config_str}
"""

# ❌ Bad - Inconsistent formatting
prompt = f"""
Input: {json.dumps(input_data, indent=2)}
Expected format: {config_schema}
"""
```

### 4. Handle Lists and Nested Structures
```python
# Complex nested structure
data = {
    "proteins": [
        {"name": "NMNAT2", "id": "P39748"},
        {"name": "PARTNER1", "id": "Q12345"}
    ],
    "metadata": {
        "timestamp": datetime.now(),
        "path": Path("./data")
    }
}

# Serialize everything
json_str = json.dumps(data, indent=2, default=str)
```

## Common Use Cases

### Use Case 1: Serializing History Lists
```python
history_str = json.dumps(self.history_list[:self.num_history], indent=2, default=str)

prompt = f"""
Previous decisions:
{history_str}
"""
```

### Use Case 2: Serializing Configuration Schemas
```python
config_str = json.dumps(config_master['chai'], indent=2)

prompt = f"""
Return your response in this format:
{config_str}
"""
```

### Use Case 3: Serializing Analysis Results
```python
results = {
    "hotspots": [45, 67, 89],
    "scores": [0.85, 0.72, 0.68],
    "timestamp": datetime.now()
}

results_str = json.dumps(results, indent=2, default=str)

prompt = f"""
Analysis results:
{results_str}
"""
```

## Complete Example: All Prompt Managers

```python
import json

# RAGPromptManager
def conclusion_prompt(self):
    input_str = json.dumps(self.input_json, indent=2, default=str)
    prompt = f"Using hiper-rag output:\n{input_str}\nClean up and return as json..."
    return prompt

# BindCraftPromptManager
def running_prompt(self):
    history_str = json.dumps(self.history_list[:self.num_history], indent=2, default=str)
    config_str = json.dumps(config_master['bindcraft'], indent=2)
    prompt = f"History:\n{history_str}\nFormat:\n{config_str}"
    return prompt

# CHAIPromptManager
def running_prompt(self):
    input_str = json.dumps(self.input_json, indent=2, default=str)
    config_str = json.dumps(config_master['chai'], indent=2)
    prompt = f"Input:\n{input_str}\nFormat:\n{config_str}"
    return prompt

# MDPromptManager
def conclusion_prompt(self):
    input_str = json.dumps(self.input_json, indent=2, default=str)
    history_str = json.dumps(self.history_list[:self.num_history], indent=2, default=str)
    prompt = f"Results:\n{input_str}\nHistory:\n{history_str}"
    return prompt
```

## Summary

✅ **Always use `json.dumps()`** when embedding JSON in prompts  
✅ **Use `indent=2`** for readability  
✅ **Use `default=str`** to handle complex types  
✅ **Serialize both input data and config schemas**  
✅ **Test with complex nested structures**  

This ensures your LLM receives properly formatted, valid JSON that it can easily parse and understand.

