# 迁移任务规划

## 目标
将根目录遗留的 4 个真实模块迁移进 `gaworld/` 包，并把根目录文件改为 shim（向后兼容桥接），最终完成 flat→package 迁移。

## 现状摘要
已完成 shim 的（根目录已委托给 gaworld/）：
- city_map_system → gaworld.world.city_map
- config → gaworld.settings.CONFIG
- distributed_comm → gaworld.distributed.comm
- dynamic_behavior → gaworld.behavior.dynamic
- economy_module → gaworld.economy.finance
- environment → gaworld.env.system
- human_realism → gaworld.cognition.realism
- intervention_policy → gaworld.policy.intervention
- life_events → gaworld.events.life
- llm_providers → gaworld.llm.providers
- memory_store → gaworld.memory.store
- social_network → gaworld.social.network

**尚未迁移的（仍有真实代码）：**
1. experience_store.py → gaworld/memory/experience.py
2. avatar_generator.py → gaworld/io/avatar.py
3. simulation_visualizer.py → gaworld/apps/visualizer.py
4. extensibility.py → gaworld/hooks.py

**脚本（保留在根目录）：**
- custom_hooks.py（示例钩子，不迁移）
- analyze_wellbeing.py（分析脚本，不迁移）
- generate_agent_rag_seed.py（工具脚本，不迁移）

**入口点：**
- generative_city_sim.py：有几处 import 需从 shim 路径升级到 gaworld 直接路径

## 阶段

- [x] 阶段1：分析确认
- [x] 阶段2：迁移 experience_store → gaworld/memory/experience.py + shim
- [x] 阶段3：迁移 avatar_generator → gaworld/io/avatar.py + shim
- [x] 阶段4：迁移 simulation_visualizer → gaworld/apps/visualizer.py + shim
- [x] 阶段5：迁移 extensibility → gaworld/hooks.py + shim
- [x] 阶段6：更新 generative_city_sim.py 的 import 到 gaworld 路径
- [x] 阶段6b：修正 gaworld/ 内部 from config import → from gaworld.settings import
- [x] 阶段7：更新 pyproject.toml
- [x] 阶段8：运行测试验证（311 通过，2 失败为迁移前已有缺陷，已确认）

## 约束与注意事项
- 测试文件大量使用旧名（memory_store, city_map_system 等），shim 必须保留
- sys.modules 技巧用于模块级状态共享（experience_store 需要这种处理）
- simulation_visualizer 内部 import 要从 avatar_generator/city_map_system 改为 gaworld 路径
- experience_store 内部 `from config import CONFIG` 改为 `from gaworld.settings import CONFIG`

## 错误记录
（留空）
