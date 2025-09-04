```
aws sso login --profile llm-sandbox   
aws bedrock list-inference-profiles
uv sync
docker run -d --name redis-test -p 6379:6379 redis


uv run fds-server
cd run_agent/chat_ui && npm run dev
```

# queries
- `implement a page to showcase simple button component from Fabric Design System`
- `implement a page to showcase the 2 most useful variants of button component from Fabric Design System`
- `provide the documentations for Fabric Design System button and ansible playbook`


# command to run the Agent debug server(LangGraph Studio)
`bash fds_dev.sh`
<img width="907" height="593" alt="image" src="https://github.com/user-attachments/assets/e7d98f8d-5fba-434e-adbd-8683ff350710" />
<img width="1490" height="710" alt="image" src="https://github.com/user-attachments/assets/09829852-b1ed-487e-8512-7474816067f2" />
<img width="891" height="653" alt="image" src="https://github.com/user-attachments/assets/0fd732ae-9ac8-416a-a8d8-5f7b8516c883" />





# command to run the Agent server (Langraph events server through APIs to interact with the React ui)
```uv run fds-server
```
<img width="3024" height="22285" alt="screencapture-localhost-5173-2025-08-11-03_38_44" src="https://github.com/user-attachments/assets/2d9c69cd-46d7-4ec3-b3d2-7166edc997bf" />

# command to run the Agent cli
`fds-cli`

# swagger
[http://localhost:8000/docs](http://localhost:8000/docs)

# React ui
run_agent/chat_ui
```cd run_agent/chat_ui && npm run dev
```

<!-- 

# Dev Run
`uv run fastmcp dev main.py`

# Run
`uv run fds-mcp-server`

# install (might not work)
`uv run fastmcp install main.py`

# install (mostly works)
```
rm -rf dist
uv build
uv tool install dist/*.whl
uv tool update-shell
```

# after installing to add it to claude code
```
claude mcp list
claude mcp remove fds-mcp-server
claude mcp add -s user fds-mcp-server fds-mcp-server
claude mcp add --transport http fds-mcp http://127.0.0.1:8000/fds/mcp/
```

# List installed tools
`uv tool list`

# Uninstall the tool
`uv tool uninstall fds-mcp-server`


# mcp configuration for vs code (.vscode/mcp.json)
```
{
    "servers": {
        // "FDS-mcp-http": {
        //     "type": "sse",            
        //     "url": "http://127.0.0.1:8000/sse",
        //     "headers": {
        //         "Accept":"text/event-stream"
        //     }
        // },
        "FDS-mcp": {
            "type": "stdio",      
            "command": "uvx",
            "args": [
                "fds-mcp-server"
            ]
        },
    }
}
``` -->
