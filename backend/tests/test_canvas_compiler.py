import unittest
from app.compiler import validate_canvas_graph, compile_canvas_graph

DEFAULT_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "dataSource", "data": {"collection": "profiles"}},
        {"id": "n2", "type": "vectorSearch", "data": {"index": "persona_chunks_vector", "limit": 10}},
        {"id": "n3", "type": "filter", "data": {"field": "location", "op": "eq", "value": "San Francisco, CA"}},
        {"id": "n4", "type": "output", "data": {}}
    ],
    "edges": [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"},
        {"id": "e3", "source": "n3", "target": "n4"}
    ]
}

class TestCanvasCompiler(unittest.TestCase):
    def test_valid_default_graph(self):
        errors = validate_canvas_graph(DEFAULT_GRAPH)
        self.assertEqual(len(errors), 0)

    def test_default_post_filter_compilation(self):
        compiled = compile_canvas_graph(DEFAULT_GRAPH)
        self.assertEqual(compiled["status"], "success")
        self.assertEqual(len(compiled["pipeline"]), 2)
        self.assertIn("$vectorSearch", compiled["pipeline"][0])
        self.assertIn("$match", compiled["pipeline"][1])

    def test_pre_filter_rewired_compilation(self):
        rewired_graph = {
            "nodes": DEFAULT_GRAPH["nodes"],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n3"},
                {"id": "e2", "source": "n3", "target": "n2"},
                {"id": "e3", "source": "n2", "target": "n4"}
            ]
        }
        compiled = compile_canvas_graph(rewired_graph)
        self.assertEqual(compiled["status"], "success")
        self.assertIn("$match", compiled["pipeline"][0])
        self.assertIn("$vectorSearch", compiled["pipeline"][1])

    def test_cycle_detection(self):
        cyclic_graph = {
            "nodes": DEFAULT_GRAPH["nodes"],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n2"}
            ]
        }
        errors = validate_canvas_graph(cyclic_graph)
        self.assertTrue(any("Cyclic" in err for err in errors))

if __name__ == "__main__":
    unittest.main()
