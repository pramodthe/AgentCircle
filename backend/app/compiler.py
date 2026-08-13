"""
Vector Beast Canvas Topology Graph Compiler for AgentCircle.
Compiles drag-and-drop node graphs into executable MongoDB Atlas aggregation pipelines.
"""

from typing import List, Dict, Any, Tuple

VALID_NODE_TYPES = {"dataSource", "llmAgent", "filter", "vectorSearch", "rerank", "output"}

def validate_canvas_graph(graph: Dict[str, Any]) -> List[str]:
    """Validates canvas graph for disconnected nodes, invalid types, and cycles."""
    errors = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    if not nodes:
        errors.append("Canvas contains no nodes. Add at least one Data Source and Output node.")
        return errors

    node_map = {n["id"]: n for n in nodes if "id" in n}

    # Verify node types
    for node in nodes:
        n_id = node.get("id")
        n_type = node.get("type")
        if n_type not in VALID_NODE_TYPES:
            errors.append(f"Node {n_id} has invalid node type '{n_type}'.")

    # Verify edge endpoints exist
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in node_map:
            errors.append(f"Edge {edge.get('id')} references non-existent source node '{src}'.")
        if tgt not in node_map:
            errors.append(f"Edge {edge.get('id')} references non-existent target node '{tgt}'.")

    if errors:
        return errors

    # Check for disconnected nodes (if graph has > 1 node and edges exist)
    if len(nodes) > 1 and edges:
        connected_ids = set()
        for edge in edges:
            connected_ids.add(edge.get("source"))
            connected_ids.add(edge.get("target"))
        disconnected = [n["id"] for n in nodes if n["id"] not in connected_ids]
        if disconnected:
            errors.append(f"Disconnected node(s) detected: {', '.join(disconnected)}. All nodes must be connected.")

    # Cycle Detection (DFS)
    adj = {n["id"]: [] for n in nodes}
    for edge in edges:
        if edge.get("source") in adj:
            adj[edge.get("source")].append(edge.get("target"))

    visited = {}  # 0 = unvisited, 1 = visiting, 2 = visited
    cycle_found = False

    def dfs(node_id):
        nonlocal cycle_found
        visited[node_id] = 1
        for neighbor in adj.get(node_id, []):
            if visited.get(neighbor, 0) == 1:
                cycle_found = True
                return
            elif visited.get(neighbor, 0) == 0:
                dfs(neighbor)
        visited[node_id] = 2

    for node in nodes:
        node_id = node["id"]
        if visited.get(node_id, 0) == 0:
            dfs(node_id)
            if cycle_found:
                break

    if cycle_found:
        errors.append("Cyclic connection detected in canvas graph. Aggregation pipelines must be acyclic (DAG).")

    return errors

def get_topological_sort(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    node_map = {n["id"]: n for n in nodes}
    in_degree = {n["id"]: 0 for n in nodes}
    adj = {n["id"]: [] for n in nodes}

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
    sorted_nodes = []

    while queue:
        curr = queue.pop(0)
        sorted_nodes.append(node_map[curr])
        for neighbor in adj.get(curr, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return sorted_nodes if len(sorted_nodes) == len(nodes) else nodes

def compile_canvas_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    validation_errors = validate_canvas_graph(graph)
    if validation_errors:
        return {
            "status": "error",
            "errors": validation_errors,
            "pipeline": [],
            "executionOrder": []
        }

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    sorted_nodes = get_topological_sort(nodes, edges)

    pipeline = []
    execution_order = []
    collection = "profiles"
    rerank_config = None
    llm_config = None
    query_text = "Find friends with common interests"

    for node in sorted_nodes:
        n_id = node["id"]
        n_type = node.get("type")
        data = node.get("data", {})
        execution_order.append(f"{n_id} ({n_type})")

        if n_type == "dataSource":
            collection = data.get("collection", "profiles")

        elif n_type == "llmAgent":
            query_text = data.get("prompt", query_text)
            llm_config = {
                "provider": data.get("provider", "anthropic"),
                "model": data.get("model", "claude-3-5-sonnet-20241022"),
                "prompt": query_text
            }

        elif n_type == "filter":
            field = data.get("field", "location")
            op = data.get("op", "eq")
            val = data.get("value", "San Francisco")
            mongo_op = "$eq" if op == "eq" else f"${op}"
            pipeline.append({
                "$match": {
                    field: {mongo_op: val}
                }
            })

        elif n_type == "vectorSearch":
            index_name = data.get("index", "persona_chunks_vector")
            path = data.get("path", "chunk_embedding")
            limit = int(data.get("limit", 10))
            num_candidates = limit * 5
            
            pipeline.append({
                "$vectorSearch": {
                    "index": index_name,
                    "path": path,
                    "queryText": query_text,
                    "numCandidates": num_candidates,
                    "limit": limit
                }
            })

        elif n_type == "rerank":
            rerank_config = {
                "provider": data.get("provider", "voyage"),
                "model": data.get("model", "voyage-rerank-2"),
                "topK": int(data.get("topK", 5))
            }

    return {
        "status": "success",
        "collection": collection,
        "queryText": query_text,
        "pipeline": pipeline,
        "rerankConfig": rerank_config,
        "llmConfig": llm_config,
        "executionOrder": execution_order,
        "errors": []
    }
