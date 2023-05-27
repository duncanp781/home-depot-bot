import re
import json
import random
import requests
from bs4 import BeautifulSoup

from langchain import LLMChain
from langchain.schema import (
    AIMessage,
    HumanMessage,
    SystemMessage,
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

from slack_bolt import App

import os

from dotenv import load_dotenv
load_dotenv()



# TOOLS:

# Takes a plain-text query, like 'grills'.
# Query-type can be a few different things. 'b' for categories, 'p' for pages


def get_links(query, query_type='b'):
    url = f'https://homedepot.com/s/{query}?NCNI-5'

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0'}
    response = requests.get(url, headers=headers)

    soup = BeautifulSoup(response.text, features='lxml')
    links = soup.find_all('a', href=True)

    # The links in the anchors are relative, so start with /
    query_regex = r'^/' + re.escape(query_type) + r'/.*'
    cat_links = [
        f'https://homedepot.com{link["href"]}' for link in links if re.match(query_regex, link['href'])]
    return cat_links


@tool
def get_homedepot_pages(query):
    """Use this to find the url for products on the home depot website.
    You should ask for the names of products.
    Be specific: 'propane grill' gives better results than 'grill'
    It will return a sentence telling you a product and its url.
    Respond only with information gained from this tool.
    """
    page_links = get_links(query, 'p')
    pages_split = [[link] + link.split('/')[3:] for link in page_links]
    selected_page_index = random.randrange(len(pages_split))
    page = pages_split[selected_page_index]

    page_dict = {'link': page[0], 'page-type': page[1],
                 'name': page[2].replace('-', ' ')}
    page_string = f'A product with name {page_dict["name"]} is available at the url {page_dict["link"]}. '
    return page_string


page_url = "https://www.homedepot.com/p/Nexgrill-4-Burner-Propane-Gas-Grill-in-Black-with-Side-Burner-and-Stainless-Steel-Main-Lid-720-0925P/310654539"
headers = {
    "User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"}
response = requests.get(page_url, headers=headers)

# This is to add periods to prices for products, since they are missing from the html.


def add_period(text):
    digits = ''.join([char for char in text if char.isdigit()])
    fixed_digits = digits[:-2] + '.' + digits[-2:]
    return text.replace(digits, fixed_digits)

@tool
def get_homedepot_page_info(url):
    """Use this to get information about the product located at this url.
    The url passed in must look like https://homedepot.com/p/...,
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, features='lxml')
    out = ""

    product_details = soup.find("div", class_="product-details")
    if product_details:
        name = product_details.find('h1')
        if name:
            name_text = name.text.strip()
        else:
            name_text = "Name not found"

        company = product_details.find('h2')
        if company:
            company_text = company.text.strip()
        else:
            company_text = "Company not found"
    else:
        name_text = "Name not found"
        company_text = "Company not found"

    price = soup.select_one('div[class^="price"]')
    if price and len(price.text.strip()) > 1:
        price_text = "Price: " + price.text.strip()
        # The prices are missing periods before the cents
        if len(price_text) > 2:
            price_text = add_period(price_text)
    else:
        price_text = "Price information not found"

    desc = soup.find('ul', class_='sui-list-disc')
    if desc:
        desc_text = "Item Description:"
        for li in desc.find_all('li')[:-1]:
            desc_text += ' ' + li.text
    else:
        desc_text = "Description not found"

    out = f"At url {url} is the item named {name_text} from company {company_text}. {desc_text}. {price_text}. "
    return out


# LANGCHAIN:

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
    tools = [get_homedepot_pages, get_homedepot_page_info]

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


def test_agent(queries):
    agent_executor = create_homedepot_agent()
    for query in queries:
        print(agent_executor.run(query))

# test_prompts = ["Tell me about a charcoal grill and a propane grill"]
# test_agent(test_prompts)


# SLACK
slack_token = os.environ.get("SLACK_BOT_TOKEN")
slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET")

app = App(token=slack_token, signing_secret=slack_signing_secret)
req_url = "https://6eb0-98-216-177-60.ngrok-free.app/slack/events"

@app.message('hello')
def respond_to_hello(message, say):
    say("Hello!")


@app.message()
def respond_to_message(message, say):
    # if message.get('channel') == 'home-depot-bot':
    # channel id = "C05AG2JB2BS"
    text = message.get('text')
    response = helper_agent.run(text)
    say(response)

helper_agent = create_homedepot_agent()
if __name__ == "__main__":
    app.start(port=int(os.environ.get("PORT", 3000)))
    
