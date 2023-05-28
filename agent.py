from langchain import LLMChain
from langchain.schema import (
    AgentAction,
    AgentFinish
)
from langchain.agents import tool, AgentExecutor
from typing import List, Union
from langchain.llms import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.prompts import StringPromptTemplate
from langchain.tools import BaseTool
from langchain.agents import initialize_agent,  AgentType, Tool, LLMSingleActionAgent, AgentOutputParser
from langchain.memory import ConversationBufferWindowMemory

from scraping import scraping_tools

import re

from dotenv import load_dotenv
load_dotenv()

class CustomOutputParser(AgentOutputParser):
    def parse(self, llm_output: str) -> Union[AgentAction, AgentFinish]:
        # Check if agent should finish
        if "Final Answer:" in llm_output:
            return AgentFinish(
                return_values={"output": llm_output.split(
                    "Final Answer:")[-1].strip()},
                log=llm_output,
            )
        # Parse out the action and action input
        regex = r"Action\s*\d*\s*:(.*?)\nAction\s*\d*\s*Input\s*\d*\s*:[\s]*(.*)"
        match = re.search(regex, llm_output, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse LLM output: `{llm_output}`")
        action = match.group(1).strip()
        action_input = match.group(2)
        # Return the action and action input
        return AgentAction(tool=action, tool_input=action_input.strip(" ").strip('"'), log=llm_output)


# Set up a prompt template
class CustomPromptTemplate(StringPromptTemplate):
    # The template to use
    template: str
    # The list of tools available
    tools: List[Tool]

    def format(self, **kwargs) -> str:
        # Get the intermediate steps (AgentAction, Observation tuples)
        # Format them in a particular way
        intermediate_steps = kwargs.pop("intermediate_steps")
        thoughts = ""
        for action, observation in intermediate_steps:
            thoughts += action.log
            thoughts += f"\nObservation: {observation}\nThought: "
        # Set the agent_scratchpad variable to that value
        kwargs["agent_scratchpad"] = thoughts
        # Create a tools variable from the list of tools provided
        kwargs["tools"] = "\n".join(
            [f"{tool.name}: {tool.description}" for tool in self.tools])
        # Create a list of tool names for the tools provided
        kwargs["tool_names"] = ", ".join([tool.name for tool in self.tools])
        return self.template.format(**kwargs)


def create_homedepot_agent():
    tools = scraping_tools + []

    input_variables = ["input", "intermediate_steps", "history"]

    TEMPLATE = """Answer the following questions as best you can.
     You are a Home Depot help bot. People ask you questions about products, and you answer with information from the home depot website. Do not ask follow-up questions. You have access to the following tools:

    {tools}

    Use the following format:

    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of the tools.
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat up to 5 times)
    Thought: I now know the final answer
    Final Answer: the final answer to the original input question

    Previous Conversation History:
    {history}

    New Question: {input}
    {agent_scratchpad}"""

    prompt = CustomPromptTemplate(template=TEMPLATE,
                                  tools=tools,
                                  input_variables=input_variables)

    memory = ConversationBufferWindowMemory(k=2)

    llm = OpenAI(temperature=0)

    agent = LLMSingleActionAgent(
        llm_chain=LLMChain(llm=llm,
                           prompt=prompt),
        output_parser=CustomOutputParser(),
        stop=["\nObservation:"],
        allowed_tools=tools
    )

    agent_executor = AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=tools,
        verbose=True,
        memory=memory
    )
    return agent_executor

#Runs the agent against an array of queries and prints the answer
def test_agent(queries):
    agent_executor = create_homedepot_agent()
    for query in queries:
        print(agent_executor.run(query))


