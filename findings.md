# 研究与发现

## 项目结构
- 这是 flat→package 的中途迁移，pyproject.toml 注释明确说明 "still mid-migration"
- 大多数模块已经完成 shim 迁移，只剩 4 个真实模块未迁移

## 待迁移的 4 个模块分析

### experience_store.py
- 功能：Agent 的 episodes/habits/intentions/relationships 持久化
- 依赖：`from config import CONFIG`（需改为 gaworld.settings）
- 目标：`gaworld/memory/experience.py`
- 测试文件：`test_episode_persistence_across_days.py` 用 `from experience_store import ...`

### avatar_generator.py
- 功能：生成 SVG 头像
- 依赖：标准库（hashlib, os, html）
- 目标：`gaworld/io/avatar.py`
- 测试文件：间接被 simulation_visualizer 使用

### simulation_visualizer.py
- 功能：SimulationVisualizer 类，记录仿真帧
- 依赖：`from avatar_generator import ensure_agent_avatar`（改为 gaworld.io.avatar）
         `from city_map_system import project_to_tile`（改为 gaworld.world.city_map）
- 目标：`gaworld/apps/visualizer.py`
- 测试文件：`test_simulation_visualizer.py` 用旧路径

### extensibility.py
- 功能：HookBus 类（生命周期钩子调度器）
- 依赖：`from gaworld.logging_setup import get_logger`（已经是 gaworld 路径）
- 目标：`gaworld/hooks.py`

## generative_city_sim.py import 变更
需要将以下 shim import 升级为直接 gaworld 路径：
- `from config import CONFIG` → `from gaworld.settings import CONFIG`
- `from city_map_system import ...` → `from gaworld.world.city_map import ...`
- `from distributed_comm import ...` → `from gaworld.distributed.comm import ...`
- `from dynamic_behavior import ...` → `from gaworld.behavior.dynamic import ...`
- `from extensibility import HookBus` → `from gaworld.hooks import HookBus`
- `from environment import ...` → `from gaworld.env.system import ...`
- `from llm_providers import ...` → `from gaworld.llm.providers import ...`
- `from simulation_visualizer import ...` → `from gaworld.apps.visualizer import ...`
- `from experience_store import ...` → `from gaworld.memory.experience import ...`
- `from human_realism import ...` → `from gaworld.cognition.realism import ...`

## shim 模式
两种模式：
1. sys.modules 别名（用于有模块级状态的模块）：city_map_system, memory_store 等
2. 简单 re-export（用于只导出符号的）：config.py

experience_store 建议用 sys.modules 别名，因为测试中有 `experience_store.xxx = ...` 这类写法的风险
