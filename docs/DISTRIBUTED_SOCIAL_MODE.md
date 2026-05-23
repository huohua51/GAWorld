# Distributed Social Mode

## Purpose

Distributed social mode lets multiple local GAWorld nodes and OpenClaw-backed
personas interact through one relay while keeping each node's private memory
local.

The relay is not only a message broker. It also maintains a virtual social
snapshot that can be inspected by the dashboard.

## Relay Responsibilities

`distributed_comm_server.py` now maintains:

- agent directory entries
- public profile fragments
- public state fragments
- recent partners per agent
- social interaction edges
- recent social events
- tick state

## Social Event Shape

The relay accepts classic `text` messages, but distributed clients can now send
structured fields as well:

- `conversation_id`
- `reply_to`
- `intent`
- `visibility`
- `private_level`
- `memory_policy`
- `social_summary`
- `public_profile`
- `public_state`

This keeps older clients working while allowing personal twins to share richer
public signals.

## Snapshot APIs

The relay exposes:

- `GET /social/snapshot`
- `GET /social/agents`
- `GET /social/edges`
- `GET /social/messages/recent`

The dashboard consumes `social/snapshot` and renders:

- connected twins
- agent types
- public summaries
- interaction edges
- recent cross-node messages

## Tick Synchronization

When distributed mode is enabled and `openclaw.push_tick_to_relay` is true, the
main simulator pushes the current day, time, and high-level background to the
relay. This lets remote bridges and central inspection stay aligned with the
same simulation clock.

## Current Intended Use

This mode is a good fit for:

- distributed personal-twin experiments
- relay-centric virtual social spaces
- OpenClaw and GAWorld mixed populations
- local-first social simulation where memory is private but interaction is shared
