import asyncio
import sys
import os
import json
from typing import Optional
from contextlib import AsyncExitStack
import aiohttp

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.stdio = None
        self.write = None

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server"""
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        self.http_session = await self.exit_stack.enter_async_context(aiohttp.ClientSession())

        await self.session.initialize()

        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using Groq API and available tools"""
        messages = [{"role": "user", "content": query}]
        final_text = []

        try:
            # List available tools
            response = await self.session.list_tools()
            available_tools = [
                {"name": tool.name, "description": tool.description, "input_schema": tool.inputSchema}
                for tool in response.tools
            ]

            # Convert tools to Groq format
            groq_tools = []
            for tool in available_tools:
                try:
                    groq_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool["input_schema"]
                        }
                    })
                except KeyError as e:
                    print(f"Error converting tool {tool.get('name')}: {e}")

            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"
            }
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "tools": groq_tools,
                "tool_choice": "auto",
                "max_tokens": 1000
            }

            async with self.http_session.post(url, headers=headers, json=data) as resp:
                if resp.status != 200:
                    error = await resp.json()
                    raise Exception(f"Groq API error: {error.get('error', 'Unknown error')}")
                response_data = await resp.json()

            msg = response_data["choices"][0]["message"]
            if content := msg.get("content"):
                final_text.append(content)
            tool_calls = msg.get("tool_calls", [])

            # Execute each tool call
            for call in tool_calls:
                tool_name = call["function"]["name"]
                args_raw = call["function"].get("arguments")
                try:
                    tool_args = json.loads(args_raw)
                except Exception:
                    tool_args = args_raw

                try:
                    result = await self.session.call_tool(tool_name, tool_args)

                    # Extract raw text from TextContent wrapper if present
                    rc = getattr(result, 'content', None)
                    if hasattr(rc, 'text'):
                        raw_content = rc.text
                    else:
                        raw_content = rc

                    # If the tool itself signaled an error
                    if getattr(result, 'error', False):
                        final_text.append(f"⚠️ Tool error: {raw_content}")
                        continue

                    # Pretty-print JSON if possible
                    try:
                        parsed = json.loads(raw_content)
                        formatted = json.dumps(parsed, indent=2)
                    except Exception:
                        formatted = str(raw_content)

                    final_text.append(f"🔧 Tool {tool_name} result:\n{formatted}")

                    # Append tool result for follow-up, including tool_call_id
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": tool_name,
                        "content": formatted
                    })

                    # Follow-up analysis
                    followup = {"model": "llama-3.3-70b-versatile", "messages": messages, "max_tokens": 1000}
                    async with self.http_session.post(url, headers=headers, json=followup) as fu:
                        if fu.status != 200:
                            err = await fu.json()
                            raise Exception(f"Groq API error: {err.get('error', 'Unknown error')}")
                        fu_data = await fu.json()

                    if fu_data.get("choices"):
                        fa = fu_data["choices"][0]["message"].get("content")
                        if fa:
                            final_text.append(f"📝 Final analysis:\n{fa}")

                except Exception as e:
                    final_text.append(f"❌ Tool execution failed: {e}")

        except Exception as e:
            final_text.append(f"🚨 Critical error processing query: {e}")

        return "\n".join(final_text)

    async def chat_loop(self):
        print("\nMCP Client Started! Type your queries or 'quit' to exit.")
        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() == 'quit':
                    break
                print("\n" + await self.process_query(query))
            except Exception as e:
                print(f"Error: {e}")

    async def cleanup(self):
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <server_script>")
        sys.exit(1)
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
