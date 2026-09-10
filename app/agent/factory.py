from langchain.agents import create_agent

from app.agent.llm import get_llm
from app.agent.prompts import SYSTEM_PROMPT
from app.schemas import CarhistState, Context
from app.tools import TOOLS


def create_carhist_agent():
    llm = get_llm()
    return create_agent(
        model=llm,
        tools=TOOLS,
        context_schema=Context,
        state_schema=CarhistState,
        system_prompt=SYSTEM_PROMPT,
    )
