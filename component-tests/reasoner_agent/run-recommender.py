"""A script that only runs the recommender segment of the reasoning system"""
import asyncio

import httpx

from struct_bio_reasoner.agents.language_model.langchain_agent import LangChainAgent

async def main():
    agent = LangChainAgent(
        research_goal="Design IL-6 binder",
        enabled_agents=["computational_design", "molecular_dynamics"],
        llm_provider="nim",
        target_protein="MKKLL",
        base_url='http://127.0.0.1:18000/v1/',
        model_name='nvidia/llama-3.1-nemotron-nano-8b-v1',
        timeout=httpx.Timeout(None),
    )
    result = await agent.generate_recommendation(
        results={"results": "none"},
        previous_run="starting",
        history={},
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
