# Recommender Testing

Ensure that we can run the basic endpoints for the Recommender Agent.

## Installation

The test is currently hard-coded to expect a locally-hosted NIM running `nvidia/llama-3.1-nemotron-nano-8b-v1`.
on http://127.0.0.1:18000/v1/.

The test also requires installing SBR with the `nvidia` optional dependencies, 
which includes the [NVIDIA endpoints for LangChain](https://pypi.org/project/langchain-nvidia-ai-endpoints/).
