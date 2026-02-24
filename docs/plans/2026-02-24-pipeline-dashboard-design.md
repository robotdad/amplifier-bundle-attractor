# Attractor Pipeline Dashboard Design

## Goal

Build a real-time pipeline monitoring dashboard for the Attractor pipeline orchestration system. The dashboard renders directed graphs (DOT-based pipelines) with execution state overlaid, enabling developers to monitor running pipelines, drill into node details, and inspect historical runs.

Two audiences:

1. **Developers** actively monitoring pipeline runs
2. **Service operators** viewing fleet status across multiple pipeline instances

## Background

Attractor pipelines are defined as DOT graphs and executed by the pipeline orchestrator. During execution, nodes transition through states (pending, running, success, failed, retrying, skipped) as LLM calls complete and edge routing decisions are made. Currently there is no visual way to observe this execution -- developers rely on log output. A dashboard would provide real-time visual feedback, historical analysis, and fleet-level monitoring.

The key architectural constraint is that the dashboard server runs as a **separate process** from the pipeline sessions. The richest data source (`pipeline.state` contribution channel) is in-process only. This means state must cross the process boundary through a shared store -- and CXDB already captures pipeline events via its event store hook (PR #18).

## Key Design Decisions

1. **Standalone web app** -- separate repo (`amplifier-dashboard-attractor`), no dependency on amplifier-core
2. **CXDB as the single source of truth** -- the dashboard server is a stateless query translator over CXDB's HTTP API; no separate state management
3. **React + Vite + React Flow + ELK.js** frontend -- DOM-based graph nodes for full CSS animation support, ELK.js for DAG layout (same algorithm family as Graphviz's `dot`)
4. **FastAPI backend** -- thin stateless server querying CXDB HTTP API, serving REST + WebSocket + static SPA files
5. **Dark-theme-first** -- desaturated color palette optimized for developer monitoring sessions, triple-channel state encoding (color + border + motion) for accessibility
6. **Desktop-first with graceful degradation** -- design baseline at 1440px, functional down to 768px

## Architecture

### Tech Stack

**Frontend:**

- React 18+ with Vite (not Next.js -- no SSR needs for a dashboard)
- React Flow v12 for graph rendering with custom node components
- ELK.js (layered algorithm) for DAG layout
- ts-graphviz for parsing DOT source into topology
- Zustand for state management (already embedded in React Flow)
- CSS Modules or Tailwind with custom properties for dark theme
- Recharts or sparklines for metrics
- React Router v7 for three-view navigation

**Backend:**

- Standalone FastAPI + uvicorn
- Queries CXDB HTTP API via httpx (async HTTP client)
- No amplifier-core dependency -- fully decoupled
- Serves static SPA files
- WebSocket endpoint polls CXDB every 1-2s and pushes diffs to connected browsers

### Data Path

```
Pipeline Session -> CxdbEventStoreHook -> CXDB Server (TCP)
                                               |
Dashboard Server (FastAPI) <- CXDB HTTP API queries
                                               |
Browser (React + React Flow) <- REST + WebSocket
```

### DOT to Layout Pipeline

1. **Parse DOT:** ts-graphviz extracts nodes, edges, attributes from DOT source
2. **Layout with ELK.js:** layered algorithm positions nodes (designed for DAGs)
3. **Render with React Flow:** map ELK positions to React Flow nodes with custom components

### Deployment

Static frontend build (`npm run build` -> `dist/`), FastAPI server as a Python package. No Node.js runtime in production. Deploy to any CDN + Python host.

## Components

### Views and Information Hierarchy

Three-level drill-down with persistent application shell and breadcrumb navigation.

### Level 1: Fleet View (`/pipelines`)

Scannable list of all pipeline instances. Polling at 5s intervals. Filterable by status (running/complete/failed), sortable by recency.

Per-row data:

| Field | Description |
|---|---|
| Status indicator | Color-coded icon |
| Pipeline name | From DOT graph label |
| Status text | running / complete / failed |
| Progress | nodes_completed / nodes_total |
| Elapsed time | Wall clock duration |
| Token count | Input + output tokens |
| Source file | DOT file path |
| Relative time | "2m ago", "just now" |

Optional: tiny 120x40px graph thumbnails as visual fingerprints.

NOT shown at fleet level: graph visualization, per-node details, edge decisions, prompts, loop iterations.

### Level 2: Pipeline Detail (`/pipelines/:id`)

Graph-dominant layout. WebSocket for real-time updates.

**Layout:** CSS Grid with graph area (flexible, min 60% width) + detail panel (360px fixed, right side). Aggregate metrics bar at top (48px). Collapsed timeline at bottom.

**Graph visualization:** DOT rendered as interactive SVG with execution state overlaid via CSS classes on node/edge elements. Click node to populate detail panel. Hover for tooltip (status, duration, tokens, model, cost).

**Detail panel (right, 360px):** Shows selected node's run history (all attempts), edge routing decisions, token breakdown, goal gate results. At viewports below 1280px, becomes an overlay drawer.

The graph is rendered ONCE from DOT source at `pipeline:start`. Subsequent events ONLY mutate CSS classes (fill colors, glow animations, timing labels). No layout shifts during execution.

For graphs using `rankdir=TB`, automatically swap to graph-top/detail-bottom layout.

### Level 3: Node Drill-Down (`/pipelines/:id/nodes/:nodeId`)

Full-width forensics view. Breadcrumb preserves pipeline context.

Shows:

- Node identity (type, shape)
- All run attempts with per-attempt timing, tokens, and outcome
- The prompt text
- The LLM response text
- Edge routing decisions from this node
- Supervisor cycles if applicable
- Human interactions if applicable

### Progressive Disclosure Pattern

Glance (node color/label on graph) -> hover (tooltip with 5-6 metrics) -> click (detail panel with run history) -> navigate (full node drill-down with forensics).

## Data Flow

### CXDB Integration

The dashboard doesn't maintain its own state. CXDB is the single source of truth. Two additions are needed to the CXDB hook (on top of existing PR #18 pipeline event handlers):

**Addition 1: Pipeline labels on CXDB contexts.** On `pipeline:start`, tag the CXDB context with labels: `pipeline_id:{id}`, `pipeline_status:running`. On `pipeline:complete`, update to `pipeline_status:complete` or `pipeline_status:failed`. This enables fleet queries: `cxdb_search(label="pipeline_status:running")`.

**Addition 2: State snapshot system turns.** On each `pipeline:node_complete`, write the full `PipelineRunState.to_dict()` as a CXDB system turn payload (kind: `pipeline_state_snapshot`). This gives the dashboard pre-assembled state in one read without replaying event history. The `dot_source` field is included so the frontend can render the graph.

### Dashboard Server Endpoints

```
GET  /api/pipelines              -> cxdb_search(label="pipeline_status:*")
                                  -> return [{id, status, nodes, elapsed, tokens}]

GET  /api/pipelines/:id          -> cxdb_get_turns(context_id, item_type="system")
                                  -> find latest pipeline_state_snapshot turn
                                  -> return PipelineRunState dict (includes dot_source)

GET  /api/pipelines/:id/nodes/:nodeId
                                  -> filter turns for node-specific events
                                  -> return node run history, timing, metrics

WS   /ws/pipelines/:id           -> poll CXDB every 1-2s for new turns
                                  -> push incremental events to connected browsers
```

The dashboard server is stateless -- any instance can serve any pipeline. Multiple dashboard instances work without coordination. Historical analysis comes free from CXDB persistence.

## Visual Design

Dark-theme-first approach optimized for developer monitoring sessions.

### State Color System

Desaturated palette, dark-theme-optimized. Triple-channel encoding ensures colorblind safety.

```
State       Color (HSL)                     Border            Motion
----------- ------------------------------- ----------------- -------------------------
pending     hsl(220, 10%, 45%) gray         Dashed            None
running     hsl(175, 65%, 55%) teal/cyan    Solid + glow      Breathing pulse (2s)
success     hsl(145, 45%, 55%) sage green   Solid             Brief flash on complete
failed      hsl(0, 55%, 62%) warm coral     Solid + x icon    Shake (300ms)
retrying    hsl(35, 70%, 60%) amber         Animated dashed   Rotating dash
skipped     hsl(220, 8%, 38%) dim gray      Dotted            None
```

Color philosophy: cool hues (teal, blue-gray) for normal operation, warm hues (coral, amber) for attention-requiring states. Saturation 45-70% (not 100%) to prevent eye strain. Colorblind-safe through luminance differentiation + triple-channel backup (color + border treatment + motion).

### Surface System

```
Base:      #0f1117  (near-black with blue undertone)
Raised:    #161922  (nodes, cards)
Overlay:   #1c1f2b  (tooltips, drawers)
Hover:     #252836  (interactive states)
```

Borders (not shadows) as the primary depth mechanism -- shadows disappear on dark backgrounds. Three-tier text hierarchy using alpha-based white.

### Typography

- **Inter** for UI labels and headings
- **JetBrains Mono** for metrics, IDs, logs, and code

The font pairing signals "this is a number" vs "this is a label" without other treatment.

### Graph Node Component

```
+----------------------+
|  [icon] Node Name    |  <- Inter 13px/500
|  model-name . 2.3s   |  <- JetBrains Mono 11px/400
|  [progress bar]  73% |  <- Only when running
+----------------------+
```

Nodes: 160px min-width, 8px border-radius. Inner glow for depth (not drop shadow). CSS transitions for all state changes (300ms ease).

### Edge Rendering

| Edge State | Style |
|---|---|
| Not yet reached | Thin, dashed, dim gray |
| Data flowing | Animated dash pattern (marching ants, 1.5s cycle) |
| Complete | Solid, slightly brighter |
| Failed path | Dotted, error color, x at midpoint |

### Responsive Breakpoints

```
>=1440px    Full experience (graph + persistent 360px panel)
1280px      Comfortable (graph + narrower persistent panel)
1024px      Functional (graph + overlay drawer panel)
768px       Simplified (minimap + linearized node list)
<768px      Status-only (pipeline health, no graph)
```

## Error Handling

- **CXDB unavailable:** Dashboard server returns 503 with retry-after header. Frontend shows "Connecting to data source..." banner with automatic retry.
- **WebSocket disconnect:** Frontend reconnects with exponential backoff. On reconnect, fetches full state snapshot to resync.
- **Stale data:** Each state snapshot includes a timestamp. Frontend shows "last updated X seconds ago" when data is older than 2x the expected polling interval.
- **Missing DOT source:** If the pipeline_state_snapshot lacks dot_source, the pipeline detail view falls back to a linearized node list instead of the graph.
- **CXDB query errors:** Dashboard server logs the error and returns a structured error response. Frontend displays error inline without crashing the view.

## Testing Strategy

- **Backend:** pytest with httpx test client for FastAPI endpoints. Mock CXDB HTTP responses. Test each endpoint independently.
- **Frontend:** Vitest + React Testing Library for component tests. Test custom React Flow node components in isolation. Test state transitions (pending -> running -> success) render correct CSS classes.
- **Integration:** Playwright for end-to-end tests against a running dashboard + CXDB instance. Verify the fleet view loads, pipeline detail renders a graph, and node drill-down displays data.
- **Visual regression:** Storybook for graph node components in each state. Screenshot comparison for state color/border/motion combinations.

## Implementation Phases

```
Phase 1: CXDB Hook Enrichment
  - Add pipeline labels to contexts
  - Add state snapshot system turns
  - Verify with cxdb_get_turns that snapshots are readable

Phase 2: Dashboard Server (REST only, no WebSocket yet)
  - FastAPI app with 3 REST endpoints
  - Queries CXDB HTTP API
  - Returns JSON -- test with curl first

Phase 3: Minimal Frontend
  - Fleet table view
  - Pipeline detail with React Flow graph rendering
  - Static files served by FastAPI

Phase 4: Real-time and Polish
  - WebSocket endpoint with CXDB polling
  - Frontend live update via WebSocket
  - Node drill-down panel
  - Animations and state transitions
```

Each phase delivers standalone value. Phase 2 alone is useful for debugging pipelines via curl.

## Scope Boundaries

- No auth/multi-tenancy in v1 -- this is a dev tool
- No GraphQL -- REST + WebSocket is sufficient
- No complex build toolchain -- Vite for frontend, pip install for backend
- No mobile optimization beyond "doesn't break"
- Phase 2 routing (tool name aliasing) is handled separately via isolated profiles

## Data Model Gap

`NodeRun` needs a `response` field to store the full LLM response text. Currently only `outcome_notes` (200-char truncated) is available. For the Level 3 drill-down to show prompt/response pairs, the full response needs to be captured per run attempt.

## Open Questions

1. Should the dashboard server be its own repo (`amplifier-dashboard-attractor`) or a directory within the attractor bundle?
2. Should we use d3-graphviz (Graphviz WASM in browser) as a fallback for DOT rendering alongside React Flow + ELK.js?
3. What is the right polling interval for the WebSocket push -- 1s (responsive but chatty) or 2s (less load)?
