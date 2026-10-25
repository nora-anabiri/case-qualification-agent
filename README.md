# Case Qualification Agent

A legal intake API built with LangGraph and FastAPI. It takes a message from a potential client, checks for a conflict of interest, classifies the case, and either declines it or qualifies it with a fee structure and an assigned attorney.

## Problem

A law firm receives intake messages that need the same first checks every time. Staff compare names against past matters, judge the case type and urgency, then decide who takes the case. This project automates that first pass and leaves the final decision to a human.

## How it works

The graph has five nodes.

conflict_check -> conflict_declined -> END
conflict_check -> classify_case
classify_case -> decline -> END
classify_case -> qualified -> END

conflict_check compares the client and the opposing party against past matters. A match sends the request to conflict_declined.

classify_case sends the message to Claude Sonnet 4.5 through OpenRouter. The model returns a case type (family law, personal injury, contract dispute, criminal, or not a fit) and an urgency level (high or normal).

qualified assigns a fee structure from data/fee_rules.json and an attorney from data/attorneys.json. The agent then creates records in HubSpot through the HubSpot MCP server.

Langfuse traces each model call for token cost and latency.

## API

POST /intake

Request body:
message, client_name, opposing_party, client_email (all strings)

Response:
The final graph state, including case_type, urgency, fee_structure, and assigned_attorney.

## Setup

Python 3.11 or later is expected. Install the packages imported in main.py, then create a .env file with these variables:

OPENROUTER_API_KEY
HUBSPOT_API_KEY
LANGFUSE_PUBLIC_KEY
LANGFUSE_SECRET_KEY
LANGFUSE_HOST

Start the server with: uvicorn main:app

## Data

Every record in the data folder is synthetic. No real client, attorney, or matter appears in this repository.

## Limitations

The conflict check uses exact text matching. "Okafor Freight" does not match "Okafor Freight Services".

The conflict check flags a returning client as a conflict. A production version must separate a repeat client from an opposing party.

Matter history is a small JSON file with five records, not a database.

The model output is parsed from plain text. A malformed reply is not handled with retries.

The endpoint has no authentication.

The project has no automated tests and no accuracy evaluation of the classifier.

## Next improvements

Fuzzy name matching, a fix for the returning client case, structured model output, an evaluation set with labelled intake messages, and endpoint authentication.
