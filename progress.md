# 进度日志

## 会话 2026-05-24

### 已完成
- 代码结构分析
- 建立迁移映射表
- 写完 task_plan.md / findings.md

### 已完成（2026-05-24）
- gaworld/memory/experience.py（从 experience_store.py 迁入）
- gaworld/io/avatar.py（从 avatar_generator.py 迁入）
- gaworld/apps/visualizer.py（从 simulation_visualizer.py 迁入，内部 import 改为 gaworld 路径）
- gaworld/hooks.py（从 extensibility.py 迁入）
- 以上4个根目录文件转为 sys.modules shim
- generative_city_sim.py 所有 import 升级到 gaworld.* 直接路径
- gaworld/ 内部10个文件的 from config import CONFIG → from gaworld.settings import CONFIG
- pyproject.toml 注释更新，py-modules 补全
- 测试：311 通过，2 失败（pre-existing，与本次迁移无关，已验证）

### 已完成（2026-05-24，第二轮）
- 创建 legacy/，移入 19 个遗留 shim 文件和旧脚本
- legacy/README.md：旧模块 → 新位置对照表
- 全部测试 import 改为 gaworld.* 直接路径（含 @patch 字符串）
- mock_llm.py fixture 更新为 gaworld.llm.providers
- gaworld/ 内部残留的旧名引用（social_network, environment, llm_providers 等）全部修正
- pyproject.toml：移除 shim py-modules，更新 ruff/black/mypy exclude
- AGENTS.md 和 README.zh-CN.md 文档更新，反映新目录结构
- 测试结果：311 通过，2 失败（pre-existing，已确认与迁移无关）

### 进行中
无

### 待办
无——重构完成
