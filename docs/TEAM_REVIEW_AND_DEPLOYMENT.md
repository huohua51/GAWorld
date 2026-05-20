# GAWorld team board, review, and deployment workflow

## Shared services

Run these on the team server from the repo root:

```bash
chmod +x scripts/server_bootstrap.sh scripts/test_branch_loop.sh
APP_DIR="$HOME/GAWorld" DASHBOARD_PORT=8766 RELAY_PORT=8877 TEST_BRANCH=tf scripts/server_bootstrap.sh
```

If the server does not have GitHub credentials, deploy from a local checkout:

```bash
deploy/deploy_to_team_server.sh
```

Services:

- Team board: `http://10.72.74.13:8766/board`
- GAWorld dashboard: `http://10.72.74.13:8766/dashboard`
- Remote Agent relay: `http://10.72.74.13:8877`
- Latest test log: `output/test-logs/latest.log`
- Board data: `output/dashboard/todo_board.json`
- Relay state: `output/distributed/relay_state.json`

## Code review gate

Each contributor works on an individual branch and opens a PR into `tf`.

Required before merge:

- PR description states purpose, changed modules, and manual verification.
- `python -m pytest` passes on the long-running test server.
- Reviewer checks for behavioral regressions, test coverage for changed behavior, and compatibility with existing config/output files.
- No direct pushes to `main`; `tf` is the integration branch. Promote `tf` to `main` only after review sign-off.

Merge policy:

- Small feature branches: squash merge into `tf`.
- Shared interfaces, config, persistence, or Agent communication changes: require one extra review.
- Failing test-loop result blocks merge unless the failure is unrelated and documented in the PR.

## Remote Agent relay contract

Register an Agent:

```bash
curl -X POST http://10.72.74.13:8877/register \
  -H 'Content-Type: application/json' \
  -d '{"cluster":"default","node_id":"student-a","agents":[{"id":101,"name":"agent-101"}]}'
```

Send a message:

```bash
curl -X POST http://10.72.74.13:8877/message/send \
  -H 'Content-Type: application/json' \
  -d '{"cluster":"default","node_id":"student-a","message":{"from_agent":101,"to_agent":102,"text":"hello"}}'
```

Poll messages:

```bash
curl -X POST http://10.72.74.13:8877/message/poll \
  -H 'Content-Type: application/json' \
  -d '{"cluster":"default","recipient_ids":[102],"since":{},"limit":100}'
```
