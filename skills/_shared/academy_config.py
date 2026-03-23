"""Academy exchange configuration stubs (Layer 4).

Provides factory functions for creating Academy Exchange instances
in local (laptop) and distributed (HPC) modes.
"""

from typing import Any, Optional


def get_local_exchange_config() -> dict[str, Any]:
    """Configuration for local development mode.

    Uses Academy's LocalExchangeFactory — all agents run in-process,
    Handle calls are async method calls.
    """
    return {
        "exchange_type": "local",
        "factory": "academy.exchange.LocalExchangeFactory",
        "options": {},
    }


def get_redis_exchange_config(
    redis_url: str = "redis://localhost:6379",
    redis_db: int = 0,
) -> dict[str, Any]:
    """Configuration for distributed HPC mode.

    Uses Academy's RedisExchangeFactory — agents distributed across
    compute nodes, communication via Redis pub/sub.
    """
    return {
        "exchange_type": "redis",
        "factory": "academy.exchange.RedisExchangeFactory",
        "options": {
            "redis_url": redis_url,
            "redis_db": redis_db,
        },
    }


def get_exchange_config(
    mode: str = "local",
    **kwargs: Any,
) -> dict[str, Any]:
    """Get exchange configuration by deployment mode.

    Args:
        mode: "local" or "redis"
        **kwargs: Additional options passed to the mode-specific config

    Returns:
        Exchange configuration dictionary
    """
    if mode == "local":
        return get_local_exchange_config()
    elif mode == "redis":
        return get_redis_exchange_config(**kwargs)
    else:
        raise ValueError(f"Unknown exchange mode: {mode}. Use 'local' or 'redis'.")


# Default agent hierarchy configuration for the Executive/Manager/Worker pattern
AGENT_HIERARCHY_CONFIG = {
    "executive": {
        "description": "Strategic agent — allocates compute resources, evaluates manager performance",
        "agent_class": "struct_bio_reasoner.agents.executive.ExecutiveAgent",
    },
    "manager": {
        "description": "Tactical agent — one per RAG target, decides task sequence",
        "agent_class": "struct_bio_reasoner.agents.manager.ManagerAgent",
    },
    "workers": {
        "folding": {
            "description": "Structure prediction worker",
            "skill": "structure-prediction",
        },
        "md": {
            "description": "Molecular dynamics worker",
            "skill": "molecular-dynamics",
        },
        "bindcraft": {
            "description": "Binder design worker",
            "skill": "bindcraft",
        },
        "conservation": {
            "description": "Conservation analysis worker",
            "skill": "evolutionary-conservation",
        },
        "literature": {
            "description": "Literature mining worker",
            "skill": "hiperrag",
        },
    },
}
