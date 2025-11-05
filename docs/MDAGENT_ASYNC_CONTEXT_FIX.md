# MDAgent Async Context Manager Fix

## The Problem

When running Example 2, you encountered this error:

```
MDAgentAdapter - ERROR - MDAgent simulation failed: Handle to AgentId<bfea00be> 
can not find an exchange client to use.
```

## Root Cause

The Academy framework's `Manager` is an **async context manager** that needs to be properly entered to initialize the exchange client (the communication channel between agents).

### What Was Happening (WRONG)

```python
# Create manager but DON'T enter the context
self.manager = await Manager.from_exchange_factory(
    factory=LocalExchangeFactory(),
    executors=ThreadPoolExecutor(),
)

# Launch agents - this might work
self.builder_handle = await self.manager.launch(Builder)

# Try to use agents - ERROR!
# The exchange client was never properly initialized
```

### What Should Happen (CORRECT)

```python
# Create manager
self.manager = await Manager.from_exchange_factory(
    factory=LocalExchangeFactory(),
    executors=ThreadPoolExecutor(),
)

# ENTER the context to initialize exchange client
await self.manager.__aenter__()

# Now launch agents - exchange is ready
self.builder_handle = await self.manager.launch(Builder)

# Use agents - works!
```

## The Fix

### 1. Updated `MDAgentAdapter.initialize()`

**File**: `struct_bio_reasoner/agents/molecular_dynamics/mdagent_adapter.py`

**Changes**:
- Added `await self.manager.__aenter__()` after creating the manager
- Added proper error handling to exit context if initialization fails
- Ensures exchange client is initialized before launching agents

```python
# Create Academy manager
self.manager = await Manager.from_exchange_factory(
    factory=LocalExchangeFactory(),
    executors=ThreadPoolExecutor(),
)

# Enter the manager context to initialize exchange client
await self.manager.__aenter__()  # ← NEW!

# Now launch agents (exchange is ready)
self.builder_handle = await self.manager.launch(Builder)
self.simulator_handle = await self.manager.launch(MDSimulator)
self.coordinator_handle = await self.manager.launch(
    MDCoordinator,
    args=(self.builder_handle, self.simulator_handle)
)
```

### 2. Updated `MDAgentAdapter.cleanup()`

**Changes**:
- Improved error handling when exiting manager context
- Properly nullifies all handles after cleanup
- Ensures resources are released even if errors occur

```python
async def cleanup(self) -> None:
    """Clean up MDAgent resources."""
    try:
        if self.manager:
            try:
                await self.manager.__aexit__(None, None, None)
                self.logger.info("Academy manager context exited successfully")
            except Exception as e:
                self.logger.warning(f"Error exiting manager context: {e}")
            finally:
                # Always nullify handles
                self.manager = None
                self.builder_handle = None
                self.simulator_handle = None
                self.coordinator_handle = None
        
        await super().cleanup()
        self.logger.info("MDAgent adapter cleanup completed")
        
    except Exception as e:
        self.logger.error(f"MDAgent adapter cleanup failed: {e}")
```

### 3. Added `MDAgentAdapter.__del__()`

**Changes**:
- Added destructor to warn if cleanup wasn't called
- Safety net to detect resource leaks

```python
def __del__(self):
    """Destructor to ensure manager is cleaned up."""
    if hasattr(self, 'manager') and self.manager is not None:
        self.logger.warning("MDAgentAdapter deleted without proper cleanup - manager still active")
```

### 4. Added `MDAgentExpert.cleanup()`

**File**: `struct_bio_reasoner/agents/roles/mdagent_expert.py`

**Changes**:
- Added cleanup method to properly shut down the adapter
- Ensures Academy manager is closed when expert is done

```python
async def cleanup(self) -> None:
    """Clean up MDAgent expert resources."""
    try:
        if self.md_adapter:
            await self.md_adapter.cleanup()
            self.logger.info("MDAgent adapter cleaned up")
        
        await super().cleanup()
        self.logger.info("MDAgent Expert cleanup completed")
        
    except Exception as e:
        self.logger.error(f"MDAgent Expert cleanup failed: {e}")
```

### 5. Updated Example 2

**File**: `examples/mdagent_integration_example.py`

**Changes**:
- Added `finally` block to ensure cleanup is always called
- Prevents resource leaks between example runs

```python
try:
    await expert.initialize()
    
    if expert.initialized:
        capabilities = expert.get_capabilities()
        logger.info(f"Expert Capabilities: {capabilities}")
        # ... use expert ...
    else:
        logger.warning("MDAgent expert not initialized")
        
except Exception as e:
    logger.error(f"MDAgent expert initialization failed: {e}")
finally:
    # Always clean up the expert
    try:
        await expert.cleanup()
        logger.info("Expert cleaned up successfully")
    except Exception as e:
        logger.warning(f"Expert cleanup warning: {e}")
```

## Why This Matters

### Academy Framework Context Manager Pattern

The Academy framework uses async context managers to manage the lifecycle of:

1. **Exchange**: Communication channel between agents
2. **Manager**: Orchestrates agent lifecycle
3. **Agents**: Individual agent instances

The lifecycle is:

```
1. Create Manager
2. Enter Context (__aenter__)  ← Initializes exchange client
3. Launch Agents               ← Agents can now communicate
4. Use Agents                  ← Everything works
5. Exit Context (__aexit__)    ← Shuts down exchange
6. Destroy Manager
```

If you skip step 2, the exchange client is never initialized, and agents can't communicate.

### The Error Message Explained

```
Handle to AgentId<bfea00be> can not find an exchange client to use.
```

- **Handle**: Reference to an agent (like a phone number)
- **AgentId**: Unique identifier for the agent
- **Exchange client**: Communication channel
- **Can not find**: The exchange was never initialized (missing `__aenter__`)

## Testing the Fix

### Before the Fix

```bash
python examples/mdagent_integration_example.py --backend mdagent --example 2
```

**Result**: ❌ Error about exchange client

### After the Fix

```bash
python examples/mdagent_integration_example.py --backend mdagent --example 2
```

**Expected Result**: ✅ Should work without exchange client errors

You should see:

```
=== Example 2: MDAgent Expert Role ===
MDAgent Expert role initialized
Academy manager context entered  ← NEW!
Registered AgentId<...> in exchange
Launched agent (AgentId<...>; <class 'MDAgent.agents.Builder'>)
Launched agent (AgentId<...>; <class 'MDAgent.agents.MDSimulator'>)
Launched agent (AgentId<...>; <class 'MDAgent.agents.MDCoordinator'>)
MDAgent components initialized successfully
Expert Capabilities: {...}
Academy manager context exited successfully  ← NEW!
Expert cleaned up successfully
Example 2 completed
```

## Best Practices

### Always Use Cleanup

When using MDAgent components, always clean up:

```python
# Good pattern
adapter = MDAgentAdapter(config)
try:
    await adapter.initialize()
    # Use adapter
finally:
    await adapter.cleanup()  # Always cleanup!
```

### Or Use Async Context Manager

For future improvements, you could make the adapter itself a context manager:

```python
class MDAgentAdapter(BaseAgent):
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

# Then use it like:
async with MDAgentAdapter(config) as adapter:
    # Use adapter
    # Automatic cleanup when done
```

## Summary

**Problem**: Academy Manager wasn't being entered as a context manager, so the exchange client was never initialized.

**Solution**: 
1. Call `await manager.__aenter__()` after creating the manager
2. Call `await manager.__aexit__()` during cleanup
3. Add cleanup methods to ensure proper resource management
4. Update examples to always call cleanup

**Result**: Exchange client is properly initialized, agents can communicate, no more "can not find an exchange client" errors!

