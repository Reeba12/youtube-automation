"""Run research agent manually to test — sends topic options to ntfy."""
import sys, asyncio
sys.path.insert(0, '.')
from agents.research_agent import ResearchAgent

print("Running Research Agent — check ntfy app for topic options...")
asyncio.run(ResearchAgent().run())
print("Done.")
