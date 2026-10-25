import asyncio
import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

async def main():
    server_params = StdioServerParameters(
        command="cmd",
args=["/c", "npx", "-y", "@hubspot/mcp-server"],
        env={**os.environ, "PRIVATE_APP_ACCESS_TOKEN": os.getenv("HUBSPOT_API_KEY")}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                print(tool.name, "-", tool.description)

asyncio.run(main())