# First Grok Bot task

Outcome: Confirm you ingested Control704 wheelhouse knowledge and can rebuild or operate the stack.

Sources:
- This conversation pack: PROFILE.md, SYSTEM.md, knowledge.json
- Hosted environment: https://control704-wheelhouse-env.vercel.app
- Hosted health: https://control704-wheelhouse-env.vercel.app/api/health.json
- GitHub pack: https://github.com/doitupsolutions810-crow/control704-grokbot-knowledge

Constraints:
- Do not invent ALLOW_AGENT_EXECUTION bypasses.
- Do not invent XAI_API_KEY or claim GPU vLLM is running.
- Do not change production settings on Vercel or GitHub without approval.
- Do not echo operator API keys.

Deliverable:
1. Five-bullet system summary.
2. Table of ports and processes.
3. List of 20 task slugs.
4. Exact live command for incident_assessment.
5. Open questions (keys, credits, real vLLM host).

Review point: Stop after the deliverable. Ask before creating repos, spending credits, or starting listeners on a machine you do not own.
