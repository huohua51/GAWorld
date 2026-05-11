"""Behavior, media exposure, and intervention defaults."""

from __future__ import annotations

from typing import Any


def news_settings() -> dict[str, Any]:
    return {
        # News / social media reading
        "news": {
            "enabled": True,
            "sources_path": "data/news_source.md",
            "cache_path": "data/news_cache.json",
            "use_cache_first": True,
            "daily_chance": 0.9,
            "max_reads_per_day": 5,
            "timeout": 8,
            "max_chars": 2000,
            "memory_excerpt_chars": 600,
            "user_agent": "GAWorld/1.0",
            "info_seek": {
                "enabled": True,
                "base_daily_chance": 0.55,
                "max_seeks_per_day": 3,
                "preferred_sites_per_agent": 6,
                "prefer_source_visit_ratio": 0.55,
                "engines": ["baidu", "google", "bing"],
                "max_results": 4,
                "timeout": 8,
                "content_timeout": 8,
                "content_max_chars": 2000,
                "memory_excerpt_chars": 700,
                "user_agent": "GAWorld/1.0",
            },
        },
    }


def intervention_settings() -> dict[str, Any]:
    return {
        # PolicySim-inspired lightweight intervention evaluation.
        # This is deterministic and does not call external moderation or training APIs.
        "intervention": {
            "enabled": True,
            "output_dir": "output/intervention",
            "recommendation": {
                "max_items": 5,
                "source_weights": {
                    "relational": 1.0,
                    "personalized": 0.85,
                    "headline": 0.75,
                },
            },
            "exposure_control": {
                "enabled": True,
                "toxicity_threshold": 0.45,
                "misinformation_threshold": 0.35,
                "suppression_factor": 0.25,
            },
            "stance": {
                "alpha": 0.8,
                "positive_keywords": ["支持", "赞成", "改善", "安心", "信任", "机会", "合作", "透明", "保护"],
                "negative_keywords": ["反对", "担心", "不满", "风险", "冲突", "失望", "质疑", "压力", "限制"],
            },
            "toxicity_keywords": ["辱骂", "攻击", "仇恨", "歧视", "极端", "滚", "骗子", "垃圾"],
            "misinformation_keywords": ["谣言", "假消息", "未经证实", "阴谋", "伪造", "骗局", "造假", "不实"],
            "objectives": {
                "cross_viewpoint_weight": 0.55,
                "engagement_weight": 0.20,
                "toxicity_penalty_weight": 0.15,
                "misinformation_penalty_weight": 0.10,
            },
        },
    }


def human_realism_settings() -> dict[str, Any]:
    return {
        # Human realism (experience accumulation + habit/need dynamics)
        "human_realism": {
            "enabled": True,
            "llm": {
                "max_extra_calls_per_agent_day": 2,
            },
            "memory": {
                "max_episodes_per_agent": 2000,
                "daily_consolidation_top_k": 12,
                "salience_threshold": 0.35,
                "decay_half_life_days": 14,
                "recall": {
                    "base_top_k": 2,
                    "max_top_k": 5,
                    "planning_top_k": 3,
                    "action_top_k": 3,
                    "reflection_top_k": 4,
                    "interview_top_k": 4,
                    "hint_chars": 240,
                    "surface_min_score": 0.08,
                    "effect_scale": 0.015,
                },
                "review": {
                    "interval_minutes": 240,
                    "max_per_day": 3,
                    "trigger_salience": 0.72,
                    "top_k": 4,
                },
            },
            "behavior": {
                "habit_learning_rate": 0.08,
                "inertia_weight": 0.25,
                "decision_noise": 0.18,
                "fatigue_work_gain": 0.035,
                "fatigue_sleep_recovery": 0.18,
                "self_control_recovery": 0.08,
                "time_pressure_decay": 0.06,
                "commitment_weights": {
                    "high": 1.2,
                    "medium": 0.6,
                    "low": 0.2,
                },
                "avoidance_bonus_scale": 1.1,
                "need_weights": {
                    "energy": 0.45,
                    "hunger": 0.30,
                    "social_need": 0.25,
                },
            },
        },
        # Dynamic behaviour system: spontaneous urges, social encounters,
        # need-based interrupts, and environment-triggered activity changes.
        "dynamic_behavior": {
            "enabled": True,
        },
    }
