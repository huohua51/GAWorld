import os
import tempfile
import unittest

from gaworld.world.city_map import distance_between, load_city_map, shortest_path, travel_plan
from scripts.generate_citymap import generate_citymap


class TestCityMapSystem(unittest.TestCase):
    def test_city_map_has_coordinates_edges_and_overlays(self):
        city_map = load_city_map("citymap.md")
        self.assertIn("nodes", city_map)
        self.assertIn("edges", city_map)
        self.assertIn("metro_lines", city_map)
        self.assertIn("river", city_map)
        self.assertGreater(len(city_map["nodes"]), 10)
        self.assertGreater(len(city_map["edges"]), 10)
        self.assertGreaterEqual(len(city_map["metro_lines"]), 1)
        central = city_map["nodes"]["Central Block"]
        self.assertIn("lat", central)
        self.assertIn("lng", central)

    def test_travel_plan_returns_distance_mode_and_route(self):
        city_map = load_city_map("citymap.md")
        agent = {"job": "算法工程师", "daily_life": "平时通勤上班"}
        plan = travel_plan(agent, city_map, "Central Block", "Hangzhou Tech Labs", activity="通勤上班")
        self.assertGreater(plan["distance_km"], 0.1)
        self.assertIn(plan["mode"], {"walk", "bike", "e-bike", "bus", "metro", "car", "taxi"})
        self.assertGreaterEqual(plan["travel_minutes"], 1)
        self.assertGreaterEqual(len(plan["route"]), 2)
        self.assertGreater(distance_between(city_map, "Central Block", "Hangzhou Tech Labs"), 0.1)
        self.assertGreaterEqual(len(shortest_path(city_map, "Central Block", "Hangzhou Tech Labs")), 2)

    def test_explicit_directives_are_parsed(self):
        content = """# City Map\n@river: Demo River | path=0.1,0.2;0.5,0.2;0.9,0.4 | width=0.05\n@node: Alpha Hub | kind=hub | category=commerce | x=3.0 | y=4.0\n@node: Beta Hub | kind=hub | category=transit | x=7.0 | y=4.0\n@road: Alpha Hub -> Beta Hub | type=arterial | bridge=true\n@metro: M9 | color=#ff5500 | stops=Alpha Hub>Beta Hub\n\n- City: Demo\n  - Hub: Alpha Hub\n    - Nearby: A Street\n  - Hub: Beta Hub\n    - Nearby: B Street\n"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "demo.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            city_map = load_city_map(path)
        self.assertEqual("commerce", city_map["nodes"]["Alpha Hub"]["category"])
        self.assertEqual("#ff5500", city_map["metro_lines"][0]["color"])
        self.assertTrue(any(edge.get("bridge") for edge in city_map["edges"]))

    def test_generator_outputs_new_directives(self):
        generated = generate_citymap("a medium city in east china", seed=7)
        self.assertIn("@river:", generated)
        self.assertIn("@node:", generated)
        self.assertIn("@road:", generated)


if __name__ == "__main__":
    unittest.main()
