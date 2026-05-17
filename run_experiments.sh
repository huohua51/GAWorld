#!/bin/bash
# GAWorld 三组对照实验并行启动脚本
# 每组实验都包含 agent 51（江晓凯·数字分身）
# 输出目录互相独立，可同时运行

cd "$(dirname "$0")"

# 先清理旧数据
echo "=== Reset all experiments ==="
for exp in exp_a exp_b exp_c; do
    rm -rf output_${exp}
done

# Reset each experiment directory so sim_state.json gets initialized correctly
GAWORLD_CONFIG_OVERRIDES='{"agent_ids":[51,1,3,10],"memory_dir":"output_exp_a/memory","log_dir":"output_exp_a/logs","visualization":{"output_dir":"output_exp_a/visualization"},"economy":{"output_dir":"output_exp_a/economy"},"environment_output_dir":"output_exp_a/environment"}' \
    python generative_city_sim.py reset 2>&1 | tail -1

GAWORLD_CONFIG_OVERRIDES='{"agent_ids":[51,5,13,20],"memory_dir":"output_exp_b/memory","log_dir":"output_exp_b/logs","visualization":{"output_dir":"output_exp_b/visualization"},"economy":{"output_dir":"output_exp_b/economy"},"environment_output_dir":"output_exp_b/environment"}' \
    python generative_city_sim.py reset 2>&1 | tail -1

GAWORLD_CONFIG_OVERRIDES='{"agent_ids":[51,7,9,4],"memory_dir":"output_exp_c/memory","log_dir":"output_exp_c/logs","visualization":{"output_dir":"output_exp_c/visualization"},"economy":{"output_dir":"output_exp_c/economy"},"environment_output_dir":"output_exp_c/environment"}' \
    python generative_city_sim.py reset 2>&1 | tail -1

# ── 实验天数（改这里）──
DAYS=7

# 实验A：同龄压力圈 — 51(江晓凯) + 1(算法工程师) + 3(在校学生) + 10(咨询分析师)
EXP_A="{\"agent_ids\":[51,1,3,10],\"memory_dir\":\"output_exp_a/memory\",\"log_dir\":\"output_exp_a/logs\",\"visualization\":{\"output_dir\":\"output_exp_a/visualization\"},\"economy\":{\"output_dir\":\"output_exp_a/economy\"},\"environment_output_dir\":\"output_exp_a/environment\",\"sim_days\":$DAYS}"

# 实验B：跨阶层混合 — 51(江晓凯) + 5(创业PM) + 13(35岁中产) + 20(民宿老板)
EXP_B="{\"agent_ids\":[51,5,13,20],\"memory_dir\":\"output_exp_b/memory\",\"log_dir\":\"output_exp_b/logs\",\"visualization\":{\"output_dir\":\"output_exp_b/visualization\"},\"economy\":{\"output_dir\":\"output_exp_b/economy\"},\"environment_output_dir\":\"output_exp_b/environment\",\"sim_days\":$DAYS}"

# 实验C：自由职业圈 — 51(江晓凯) + 7(摄影师) + 9(游戏策划) + 4(新媒体运营)
EXP_C="{\"agent_ids\":[51,7,9,4],\"memory_dir\":\"output_exp_c/memory\",\"log_dir\":\"output_exp_c/logs\",\"visualization\":{\"output_dir\":\"output_exp_c/visualization\"},\"economy\":{\"output_dir\":\"output_exp_c/economy\"},\"environment_output_dir\":\"output_exp_c/environment\",\"sim_days\":$DAYS}"

echo "=== Starting Experiment A: 同龄压力圈 [agents: 51,1,3,10] ${DAYS}天 ==="
GAWORLD_CONFIG_OVERRIDES="$EXP_A" nohup python generative_city_sim.py run \
    >> output_exp_a/run.log 2>&1 &
PID_A=$!
echo "Exp A PID: $PID_A"

echo "=== Starting Experiment B: 跨阶层混合 [agents: 51,5,13,20] ${DAYS}天 ==="
GAWORLD_CONFIG_OVERRIDES="$EXP_B" nohup python generative_city_sim.py run \
    >> output_exp_b/run.log 2>&1 &
PID_B=$!
echo "Exp B PID: $PID_B"

echo "=== Starting Experiment C: 自由职业圈 [agents: 51,7,9,4] ${DAYS}天 ==="
GAWORLD_CONFIG_OVERRIDES="$EXP_C" nohup python generative_city_sim.py run \
    >> output_exp_c/run.log 2>&1 &
PID_C=$!
echo "Exp C PID: $PID_C"

echo ""
echo "=== 三组实验已在后台运行，共 ${DAYS} 天 ==="
echo "PIDs: A=$PID_A  B=$PID_B  C=$PID_C"
echo "$PID_A $PID_B $PID_C" > output_exp_pids.txt
echo "PID 已保存至 output_exp_pids.txt"
echo ""
echo "查看进度："
echo "  tail -f output_exp_a/logs/agent_51.log"
echo "  tail -f output_exp_b/logs/agent_51.log"
echo "  tail -f output_exp_c/logs/agent_51.log"
echo ""
echo "检查是否还在跑："
echo "  cat output_exp_pids.txt | xargs -n1 ps -p 2>/dev/null"
echo ""
echo "停止所有实验："
echo "  cat output_exp_pids.txt | xargs kill"
