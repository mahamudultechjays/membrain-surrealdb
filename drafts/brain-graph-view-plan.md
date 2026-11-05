# Brain graph view: plan

Status: built on 5 Nov 2026, in `frontend/src/components/brain/graph/`. Binu asked for a graph view on Brain, after the list and filter work. The list stays the default view.

The build differs from this plan in two ways. It uses membrain's library, reagraph with its 2d/3d switch, instead of Cytoscape. The overview cap is 400 nodes, not 150, because today's context has 252 nodes, so it is drawn whole.

## Verdict

A graph view can be built with the APIs we already call. It needs no new Agent Memory endpoints and no backend change.

Checked on 5 Nov 2026 against the live context, the SDK source (`surrealdb-memory==1.0.0b1`) and https://surrealdb.com/docs/agent-memory/reference/rest-api.

## What Agent Memory gives us

| Need | Available | Notes |
|---|---|---|
| Nodes (entities) | `GET /entities` (already paged in `adapters/agent_memory/brain.py`) | No scope on entities |
| Edges (relations) | `GET /relations`: `subject`, `object`, `label`, `scope` | ~1,000 in the context today |
| Facts per node | `GET /attributes` | Already on `/api/v1/brain` |
| Chunk → entity links | Facts' `source.ref = turn:<id>` | Already on `/api/v1/brain` as `chunks[].derived` |
| One-hop expansion | `GET /entities/{type}/{name}/neighbourhood`, limit ≤ 100 | Already wrapped as `/api/v1/graph/...`; admin-only because it takes no scope |
| Multi-hop traversal or graph export | Not available | `/graph` and `/export` return 404 |
| Scope filter on entity reads | Not available | `?scope=` is ignored |

## Approach

Build the graph in the browser from the `/api/v1/brain` response the page already loads. It is already filtered to the spaces the user may read, so the graph is safe for non-admins, and every Brain filter applies to it.

- **Nodes:** one per entity that has a fact or relation in view, sized by fact count and coloured by entity type.
- **Edges:** one per relation, from `subject_ref` to `object_ref`, labelled on hover.
- **Ghost nodes:** a relation can point at an entity none of whose facts are in view. Draw it dashed, named from `object_name`.
- **Memory chunks (optional toggle):** small square nodes, each linked to the entities its facts belong to. This shows where knowledge came from.
- **Admin only, later:** "Expand" on a node calls the existing neighbourhood endpoint for neighbours outside the loaded set.

## UX

- "List | Graph" switch at the end of the filter bar's first row, with List as the default. Graph gets its own URL, `#/brain/graph`, so it can be linked.
- Default to an ego view: pick an entity, see it and its neighbours to depth 1 or 2. Drawing about 1,000 relations at once would be an unreadable hairball.
- An overview mode shows only the top 150 entities by number of connections.
- Clicking a node opens a side panel with its facts, and "Open in list" jumps to them using the list's existing reveal. Clicking an edge shows that relation.
- The list remains the accessible view. The graph canvas gets a label and a "n entities, m relations" summary.

## Library

Use Cytoscape.js with the fcose layout. It draws on canvas, copes with a few thousand elements, and has pan, zoom and selection built in.

Load it with a dynamic `import()` only when Graph is opened, so List users never download it. If graphs ever grow past about 5,000 nodes, switch to sigma.js with graphology, which draws with WebGL.

## Work breakdown (about 1.5 days)

1. `components/brain/graph.ts`: build nodes and edges from rows, count connections, and cut out ego graphs. Unit tests. (0.25 day)
2. `GraphView`: mount Cytoscape, run the layout, take colours from the theme's CSS variables in light and dark, handle resize. (0.5 day)
3. Toolbar: the List/Graph switch and route, the ego picker (reusing search), depth, and the chunk toggle. (0.25 day)
4. Side panel and the jump back into the list. (0.25 day)
5. Tests with Cytoscape mocked, `make check`, and a visual check at desktop and phone widths. (0.25 day)

## Risks

- **Hairball:** mitigated by the ego view as default and the top-150 overview.
- **"self" nodes:** Agent Memory files "I ..." statements under the speaker's principal and calls it "self". Label these with the person when the principal is known.
- **Load time:** the Brain snapshot already takes about 11 seconds. The graph adds no requests.

## Later: VCT

Once facts carry VCT node tags (Mahamudul's mapping work), the same graph can colour or cluster nodes by VCT node. That gives the "metro map" view Binu mentioned.
