# Bonus evidence mapping (maximum +6)

Bonus eligibility begins only after the required baseline cloud application works. Implementation alone does not claim a bonus mark. Keep the successful baseline artifact and the explicitly selected bonus artifact separately.

| Item | Implemented path | Required observed evidence |
| --- | --- | --- |
| B1 AI-Mode | Income UI/backend -> shared AI-Mode -> Ollama | `application-tests.json` bonus.ai_answer plus UI demonstration |
| B2 MCP | Income backend -> real MCP SDK -> Income database API | bonus.mcp and a successful UI tool call |
| B3 RAG | Income backend -> RAG retrieval -> AI-Mode generation | bonus.rag answer, citations and confidence plus UI demonstration |
| B4 Multi-Agent | Income backend -> Planner -> Worker -> Reviewer | bonus.multi_agent plan/proposal/review/audit, then a real UI human decision |
| B5 Endpoint security | HTTPS-only frontend ingress, internal backends/databases/AI, auth, safe response headers | Azure ingress configuration plus unauthenticated/cross-user refusal and headers in the application tests |
| B6 Data security | Password hashes, owner checks, runtime secret references, OIDC/managed identity, encrypted Azure Files, storage TLS restrictions | Actual `azure-controls.json` storage and secret-reference checks, code and isolation results |

Workflow artifacts are named `cloud-baseline-COMMIT` or `cloud-bonus-COMMIT`. Missing/failed artifacts mean the corresponding deployment has not been verified. The smoke test does not impersonate a human reviewer. Video evidence and final release approval must be supplied by actual team members.
