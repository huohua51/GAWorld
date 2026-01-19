import random


class EnvironmentSystem:
    def __init__(self, config, llm_fn=None):
        self.enabled = bool(config.get("enabled", True))
        self.event_chance = float(config.get("event_chance", 0.5))
        self.max_events_per_tick = int(config.get("max_events_per_tick", 1))
        self.natural_events = list(config.get("natural_events", []))
        self.social_events = list(config.get("social_events", []))
        self.llm_fn = llm_fn
        self._current_events = []

    def tick(self, day, time_str, agents=None):
        if not self.enabled:
            self._current_events = []
            return []
        events = []
        if random.random() < self.event_chance:
            candidates = []
            for name in self.natural_events:
                candidates.append({"type": "natural", "name": name, "description": name})
            for name in self.social_events:
                candidates.append({"type": "social", "name": name, "description": name})
            if candidates:
                k = min(self.max_events_per_tick, len(candidates))
                events = random.sample(candidates, k=k)
        self._current_events = events
        return events

    def get_events(self):
        return list(self._current_events)

    def get_context_text(self):
        if not self._current_events:
            return "No notable natural or social events."
        chunks = []
        for ev in self._current_events:
            chunks.append(f"{ev['type']}: {ev['description']}")
        return " ; ".join(chunks)
