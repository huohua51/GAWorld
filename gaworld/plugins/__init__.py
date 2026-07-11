"""Built-in plugin assembly.

This is the domain-side aggregation point the design doc calls
``gaworld.plugins.builtin`` — the ONE place that may import built-in plugin
classes. The kernel never imports domain logic; the simulator registers
these instances before ``registry.setup_all``.

Third-party plugins do not belong here: declare them in ``CONFIG["plugins"]``
or via the ``gaworld.plugins`` entry-point group instead.
"""

from __future__ import annotations


def builtin_plugins():
    """Instantiate the built-in plugins (K3 migration adds one per stage)."""
    from gaworld.events.plugin import LifeEventsPlugin
    from gaworld.interests_plugin import InterestsPlugin
    from gaworld.policy.plugin import InterventionPlugin
    from gaworld.skills.plugin import SkillsPlugin

    return [InterventionPlugin(), SkillsPlugin(), InterestsPlugin(), LifeEventsPlugin()]
