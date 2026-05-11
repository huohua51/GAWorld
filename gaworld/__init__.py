"""GAWorld: generative multi-agent simulator for urban social behavior.

The legacy flat layout still owns most of the codebase
(``generative_city_sim.py``, ``memory_store.py``, ``human_realism.py``…).
The ``gaworld`` package is the new home for cross-cutting concerns
introduced by the S1/S2 refactor:

* :mod:`gaworld.logging_setup` – structured logging
* :mod:`gaworld.env_loader`    – ``.env`` discovery
* :mod:`gaworld.settings`      – split legacy ``CONFIG`` assembly
* :mod:`gaworld.config`        – typed simulation configuration
* :mod:`gaworld.core.agent`    – ``Agent`` dataclass adapter
* :mod:`gaworld.io.web_scrape` – HTML / news content extraction
* :mod:`gaworld.llm.providers` – LLM provider wrappers and router

During the migration, legacy modules import from ``gaworld`` rather than
the other way around, so adopting one module at a time is safe.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.2.0"
