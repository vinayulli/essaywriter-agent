from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List
import operator
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage
from prompts import PLAN_PROMPT, WRITER_PROMPT, REFLECTION_PROMPT, RESEARCH_PLAN_PROMPT, RESEARCH_CRITIQUE_PROMPT
from pydantic import BaseModel
from tavily import TavilyClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
import streamlit as st

memory = MemorySaver()

#memory = SqliteSaver.from_conn_string(":memory:")

class AgentState(TypedDict):
    task: str
    plan: str
    draft: str
    critique: str
    content: List[str]
    revision_number: int
    max_revisions: int


class Queries(BaseModel):
    queries: List[str]

def plan_node(state: AgentState):
    messages = [
        SystemMessage(content=PLAN_PROMPT),
        HumanMessage(content=state["task"])
    ]
    response = model.invoke(messages)
    return {"plan":response.content}
def research_plan_node(state: AgentState):
    messages = [
        SystemMessage(content=RESEARCH_PLAN_PROMPT),
        HumanMessage(content=state['task'])
    ]
    queries = model.with_structured_output(Queries).invoke(messages)
    content = state.get('content',[])
    for q in queries.queries:
        response = tavily.search(query=q,max_results=2)
    for r in response['results']:
        content.append(r['content'])
    return {"content":content}
def generation_node(state: AgentState):
    content = "\n\n".join(state['content'] if state['content'] else [])
    user_message = HumanMessage(content=f"{state['task']} \n\n Here is my plan {state['plan']}")
    messages = [
        SystemMessage(content=WRITER_PROMPT.format(content=content)),
        user_message
    ]
    response = model.invoke(messages)
    return {
        "draft":response.content,
        "revision_number":state.get("revision_number",1)+1
    }
def reflection_node(state: AgentState):
    messages = [
        SystemMessage(content=REFLECTION_PROMPT),
        HumanMessage(content=state['draft'])
    ]
    response = model.invoke(messages)
    return {"critique": response.content}
def research_critique_node(state: AgentState):
    messages = [
        SystemMessage(content=RESEARCH_CRITIQUE_PROMPT),
        HumanMessage(content=state["critique"])
    ]
    queries = model.with_structured_output(Queries).invoke(messages)
    content = state["content"] or []
    for q in queries.queries:
        response = tavily.search(query=q,max_results=2)
        for r in response['results']:
            content.append(r['content'])
    return {"content":content}
def should_continue(state):
    if state["revision_number"] > state["max_revisions"]:
        return END
    return "reflect"

## Building a graph 
builder = StateGraph(AgentState)
builder.set_entry_point("planner")

builder.add_node("planner",plan_node)
builder.add_node("research_plan",research_plan_node)
builder.add_node("generate",generation_node)
builder.add_node("reflect",reflection_node)
builder.add_node("research_critique",research_critique_node)

builder.add_edge("planner","research_plan")
builder.add_edge("research_plan","generate")
builder.add_conditional_edges("generate",should_continue,{END:END,"reflect": "reflect"})
builder.add_edge("reflect","research_critique")
builder.add_edge("research_critique","generate")

graph = builder.compile(checkpointer=memory)

thread = {"configurable": {"thread_id":"1"}}

st.header("Welcome to Eassy Writer")
st.header("Enter the topic")
topic = st.text_input("Enter the topic details","")
enter_btn = st.button("Enter")

#tavily_key = st.sidebar.text_input("Enter tavily api key:")
openai_key = st.sidebar.text_input("Enter openai api key:")

if enter_btn and openai_key:
    tavily = TavilyClient(api_key="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")
    model = ChatOpenAI(model="gpt-4o-mini-2024-07-18",temperature=0.5, openai_api_key=openai_key)
    print("invoking the graph")
    output = graph.invoke({"task": topic,"max_revisions": 2,
    "revision_number": 1},thread)
    st.markdown(output['content'])
    st.text(output)






