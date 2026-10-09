# [GO-XXX] - TICKET_NAME

<!-- What does this PR change or add, and why? Which tools does it affect? -->

Related GoLinks PR: <!-- LINK_OR_REMOVE -->

## PR Approvals - [go/code-review](https://golinks.io/code-review)

- [ ] LGTM 👍
- [ ] Readability 📖
- [ ] Code Owner 🔑

## Links

| Item        | Link          |
| ----------- | ------------- |
| **_Sloom_** | LINK_TO_SLOOM |

## Type of change

- [ ] New tool
- [ ] Tool schema / response change
- [ ] Bug fix
- [ ] Auth / transport change
- [ ] Infra / CI
- [ ] Docs
- [ ] Other

## Steps to test

<!-- Local setup: https://github.com/GoLinks/golinks-mcp#local-development -->

- [ ] `.env` set up, pointing at the right GoLinks environment (e.g. `https://dev01.golinks.io/d/<YOUR_BRANCH>`)
- [ ] `uv sync` and start the server: `uv run python -m golinks_mcp`
- [ ] Connect a client (MCP Inspector, `claude mcp add --transport http golinks-mcp-dev http://localhost:8000/mcp -H "Authorization: Bearer <OAuth Token>"`, or ngrok)
- [ ] ADDITIONAL_STEPS_HERE
- [ ] Existing tools still work

1.

## More info

<!-- Screenshots, Inspector output, logs, or anything else reviewers should know -->
