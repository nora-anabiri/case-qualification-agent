from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langfuse.openai import OpenAI
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
import asyncio
import datetime
import json

load_dotenv()

matter_history = json.load(open("data/matter_history.json"))
fee_rules = json.load(open("data/fee_rules.json"))
attorneys = json.load(open("data/attorneys.json"))

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

class CaseState(TypedDict):
    message: str
    case_type: str
    urgency: str
    client_name: str
    client_email: str
    opposing_party: str
    fee_structure: str
    assigned_attorney: str

def check_conflict(state: CaseState) -> str:
    for matter in matter_history:
        if state["client_name"] in (matter["client_name"], matter["opposing_party"]):
            return "conflict"
        if state["opposing_party"] in (matter["client_name"], matter["opposing_party"]):
            return "conflict"
    return "no_conflict"

def conflict_check_node(state: CaseState) -> CaseState:
    return state

def route_after_conflict_check(state: CaseState) -> str:
    return check_conflict(state)

def conflict_declined(state: CaseState) -> CaseState:
    print(f"DECISION: Declined due to conflict of interest. {state['client_name']} or {state['opposing_party']} already appears in matter_history.")
    return state

def classify_case(state: CaseState) -> CaseState:
    prompt = f"""A potential client sent this message to a law firm:

"{state['message']}"

Reply with exactly two lines, nothing else:
case_type: <one of: family law, personal injury, contract dispute, criminal, not a fit>
urgency: <high or normal>"""

    response = client.chat.completions.create(
 name="claude-case-classification",
        model="anthropic/claude-sonnet-4.5",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.choices[0].message.content
    for line in text.split("\n"):
        if line.startswith("case_type:"):
            state["case_type"] = line.split(":", 1)[1].strip()
        if line.startswith("urgency:"):
            state["urgency"] = line.split(":", 1)[1].strip()
    return state

def route_after_classification(state: CaseState) -> str:
    if state["case_type"] == "not a fit":
        return "decline"
    return "qualified"

def decline_case(state: CaseState) -> CaseState:
    print("DECISION: Declining this case.")
    return state

def assign_fee_structure(state: CaseState) -> CaseState:
    for rule in fee_rules:
        if rule["case_type"] == state["case_type"]:
            state["fee_structure"] = rule["fee_structure"]
            return state
    state["fee_structure"] = "unassigned"
    return state

def assign_attorney(state: CaseState) -> CaseState:
    for attorney in attorneys:
        if attorney["practice_area"] == state["case_type"] and attorney["availability"] == "accepting":
            state["assigned_attorney"] = attorney["attorney_name"]
            return state
    state["assigned_attorney"] = "needs manual assignment"
    return state

async def qualified_case(state: CaseState) -> CaseState:
    state = assign_fee_structure(state)
    state = assign_attorney(state)

    server_params = StdioServerParameters(
        command="npx",
 args=["-y", "@hubspot/mcp-server"],
        env={**os.environ, "PRIVATE_APP_ACCESS_TOKEN": os.getenv("HUBSPOT_API_KEY")}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            await session.call_tool("hubspot-get-user-details", {})

            await session.call_tool("hubspot-list-objects", {
                "objectType": "contacts",
                "limit": 1
            })


            result = await session.call_tool("hubspot-batch-create-objects", {
                "objectType": "contacts",
                "inputs": [
                    {
                        "properties": {
                            "email": state["client_email"],
                            "firstname": state["client_name"],
                            "case_type": state["case_type"],
                            "urgency": state["urgency"],
                            "fee_structure": state["fee_structure"],
                            "assigned_attorney": state["assigned_attorney"]
                        }
                    }
                ]
            })

            print(f"DECISION: Qualified case created in HubSpot via MCP. Urgency: {state['urgency']}, Fee structure: {state['fee_structure']}, Attorney: {state['assigned_attorney']}")
            print("HubSpot MCP response:", result)

    return state

graph = StateGraph(CaseState)
graph.add_node("conflict_check", conflict_check_node)
graph.add_node("conflict_declined", conflict_declined)
graph.add_node("classify_case", classify_case)
graph.add_node("decline", decline_case)
graph.add_node("qualified", qualified_case)

graph.add_edge(START, "conflict_check")
graph.add_conditional_edges("conflict_check", route_after_conflict_check, {
    "conflict": "conflict_declined",
    "no_conflict": "classify_case"
})
graph.add_edge("conflict_declined", END)

graph.add_conditional_edges("classify_case", route_after_classification, {
    "decline": "decline",
    "qualified": "qualified"
})
graph.add_edge("decline", END)
graph.add_edge("qualified", END)

graph_app = graph.compile()

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class IntakeRequest(BaseModel):
    message: str
    client_name: str
    opposing_party: str
    client_email: str

@app.post("/intake")
async def intake(request: IntakeRequest):
    result = await graph_app.ainvoke({
        "message": request.message,
        "case_type": "",
        "urgency": "",
        "client_name": request.client_name,
        "client_email": request.client_email,
        "opposing_party": request.opposing_party,
        "fee_structure": "",
        "assigned_attorney": ""
    })
    return result
