from typing import TypedDict, Annotated, Sequence, List
import operator
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv

load_dotenv()  # This loads variables from .env
import os

API_KEY = os.getenv("GROQ_API_KEY")

# ==========================================
# SUPER LLM GATEWAY (Toggle switch for Local vs Production)
# ==========================================
USE_CLOUD_LLM = True

if USE_CLOUD_LLM:
    from langchain_groq import ChatGroq
    # It will read specifically from Render's config dashboard ideally, but defaults instantly to your provided token!
    API_KEY = os.getenv("GROQ_API_KEY")
    if not API_KEY:
        raise ValueError("GROQ_API_KEY environment variable is not set!")
    llm = ChatGroq(model="llama3-8b-8192", api_key=API_KEY)
else:
    from langchain_ollama import ChatOllama
    llm = ChatOllama(model="minimax-m2:cloud")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_nodes: List[str]

def greeter_node(state: AgentState, config: RunnableConfig):
    """
    Direct front-line chat. Extremely fast, zero-hop response.
    Transfers to supervisor ONLY when plans need building or finishing.
    """
    sys_msg = SystemMessage(
        content="You are the front-desk AI of a premium fitness gym. "
                "Chat warmly and concisely with the user. Answer general questions and collect details (age, weight, goal). "
                "CRITICAL INSTRUCTION: If the user provides enough details and implicitly/explicitly asks to create the workout/diet plan, OR if the user is explicitly approving/modifying an existing plan, you MUST output ONLY the exact word: TRANSFER\n"
                "Do not output TRANSFER for casual chatting. Otherwise, reply directly with helpful text."
    )
    res = llm.invoke([sys_msg] + list(state["messages"]), config=config)
    
    content = res.content.strip()
    if "TRANSFER" in content:
        return {"next_nodes": ["supervisor"]}
    else:
        return {"messages": [res], "next_nodes": []}

def supervisor_node(state: AgentState, config: RunnableConfig):
    """
    Supervisor router. Assesses conversation history.
    """
    messages = state["messages"]
    sys_msg = SystemMessage(
        content="You are a routing supervisor. Evaluate the conversation history.\n"
                "1. If the user hasn't provided details like age, weight, or specific goal, output EXACTLY: CLARIFY\n"
                "2. If the user provided details but we haven't given a plan yet, output EXACTLY: PLAN\n"
                "3. If we generated a plan previously and user hasn't approved it explicitly (didn't say yes/sounds good), output EXACTLY: APPROVAL\n"
                "4. If the user approved the plan, output EXACTLY: FINALIZE\n"
                "Respond ONLY with one of the ALL-CAPS words."
    )
    # We invoke LLM. We only take a subset of messages to save context, or all if short.
    res = llm.invoke([sys_msg] + list(messages), config=config)
    content = res.content.upper()
    
    if "CLARIFY" in content: next_n = ["clarify"]
    elif "PLAN" in content: next_n = ["coach", "nutritionist"]
    elif "APPROVAL" in content: next_n = ["ask_approval"]
    elif "FINALIZE" in content: next_n = ["manager"]
    else: next_n = ["clarify"] # fallback
    
    return {"next_nodes": next_n}

def clarify_node(state: AgentState, config: RunnableConfig):
    sys_msg = SystemMessage(content="You are a friendly AI Agent. Ask the user for missing details (age, current weight, target goal, dietary restrictions) before proceeding. Be polite and concise.")
    res = llm.invoke([sys_msg] + list(state["messages"]), config=config)
    return {"messages": [res]}

def ask_approval_node(state: AgentState, config: RunnableConfig):
    sys_msg = SystemMessage(content="You are checking for human approval. Acknowledge the plan we just generated, and explicitly ask the user if they're happy and if they approve of this plan before we finalize everything.")
    res = llm.invoke([sys_msg] + list(state["messages"]), config=config)
    return {"messages": [res]}

def coach_node(state: AgentState, config: RunnableConfig):
    sys_msg = SystemMessage(content="You are a Fitness Coach. Create a workout routine based on the user's goals. Output only the routine.")
    res = llm.invoke([sys_msg] + list(state["messages"]), config=config)
    return {"messages": [res]}

def nutritionist_node(state: AgentState, config: RunnableConfig):
    sys_msg = SystemMessage(content="You are a Sports Nutritionist. Generate a dietary meal guide based on the user's goals. Output only the diet plan.")
    res = llm.invoke([sys_msg] + list(state["messages"]), config=config)
    return {"messages": [res]}

def feedback_node(state: AgentState, config: RunnableConfig):
    sys_msg = SystemMessage(content="You are the Head Trainer. Review the previous plans generated. Provide brief, constructive feedback or a safety check.")
    res = llm.invoke([sys_msg] + list(state["messages"]), config=config)
    return {"messages": [res]}

def manager_node(state: AgentState, config: RunnableConfig):
    sys_msg = SystemMessage(content="You are the Gym Manager. The user approved! Wrap up everything into a clear, concise bulleted TO-DO LIST for Day 1.")
    res = llm.invoke([sys_msg] + list(state["messages"]), config=config)
    return {"messages": [res]}

workflow = StateGraph(AgentState)

workflow.add_node("greeter", greeter_node)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("clarify", clarify_node)
workflow.add_node("ask_approval", ask_approval_node)
workflow.add_node("coach", coach_node)
workflow.add_node("nutritionist", nutritionist_node)
workflow.add_node("feedback", feedback_node)
workflow.add_node("manager", manager_node)

workflow.add_edge(START, "greeter")

def route_greeter(state: AgentState):
    return "supervisor" if "supervisor" in state.get("next_nodes", []) else END

workflow.add_conditional_edges("greeter", route_greeter, {"supervisor": "supervisor", END: END})

def route_supervisor(state: AgentState):
    return state.get("next_nodes", ["clarify"])

workflow.add_conditional_edges("supervisor", route_supervisor, ["clarify", "coach", "nutritionist", "ask_approval", "manager"])

workflow.add_edge("clarify", END)
workflow.add_edge("ask_approval", END)

workflow.add_edge("coach", "feedback")
workflow.add_edge("nutritionist", "feedback")
workflow.add_edge("feedback", "ask_approval") # Automatically ask for approval after plan generation

workflow.add_edge("manager", END)
