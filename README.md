```
aws sso login --profile llm-sandbox   
aws bedrock list-inference-profiles 
```

# command to run the Agent server
`uv run fds-doc`

# swagger
[http://localhost:8000/docs](http://localhost:8000/docs)

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