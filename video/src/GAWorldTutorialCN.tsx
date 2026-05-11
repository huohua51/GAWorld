import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const palette = {
  ink: '#081118',
  deep: '#0f1b22',
  paper: '#f6f1e7',
  muted: '#afbec4',
  teal: '#28c7a4',
  cyan: '#62c8f2',
  amber: '#ffb84d',
  coral: '#ff7a66',
  green: '#8fd16a',
  violet: '#b8a4ff',
  line: 'rgba(219, 235, 239, 0.18)',
  panel: 'rgba(10, 22, 30, 0.78)',
};

const titleFont = '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Avenir Next", sans-serif';
const monoFont = '"SFMono-Regular", "Menlo", "Consolas", monospace';

const sceneTitle: React.CSSProperties = {
  margin: 0,
  color: palette.paper,
  fontFamily: titleFont,
  fontWeight: 750,
  fontSize: 74,
  lineHeight: 1.12,
  letterSpacing: 0,
};

const bodyText: React.CSSProperties = {
  color: palette.muted,
  fontFamily: titleFont,
  fontSize: 30,
  lineHeight: 1.55,
  letterSpacing: 0,
};

const fade = (frame: number, start: number, end: number) =>
  interpolate(frame, [start, end], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

const moveY = (frame: number, start: number, distance: number) =>
  interpolate(frame, [start, start + 22], [distance, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const drift = (frame * 0.32) % 96;

  return (
    <AbsoluteFill
      style={{
        background:
          'radial-gradient(circle at 18% 20%, rgba(40,199,164,0.22), transparent 30%), radial-gradient(circle at 78% 24%, rgba(255,184,77,0.14), transparent 26%), radial-gradient(circle at 62% 88%, rgba(98,200,242,0.16), transparent 30%), linear-gradient(180deg, #0c1820 0%, #081118 62%, #050b10 100%)',
      }}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <pattern
            id="cn-grid"
            width="96"
            height="96"
            patternUnits="userSpaceOnUse"
            patternTransform={`translate(${drift} ${drift * 0.55})`}
          >
            <path d="M 96 0 L 0 0 0 96" fill="none" stroke="rgba(180,220,228,0.1)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#cn-grid)" />
        <path
          d={`M ${width * 0.05} ${height * 0.72} C ${width * 0.28} ${height * 0.48}, ${width * 0.45} ${
            height * 0.92
          }, ${width * 0.72} ${height * 0.6} S ${width * 0.9} ${height * 0.24}, ${width * 0.96} ${height * 0.38}`}
          fill="none"
          stroke="rgba(40,199,164,0.24)"
          strokeWidth="3"
        />
      </svg>
    </AbsoluteFill>
  );
};

const Kicker: React.FC<{children: React.ReactNode; color?: string}> = ({children, color = palette.teal}) => (
  <div
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 14,
      padding: '12px 18px',
      border: `1px solid ${palette.line}`,
      borderRadius: 10,
      background: 'rgba(7, 16, 22, 0.62)',
      color,
      fontFamily: titleFont,
      fontSize: 22,
      fontWeight: 700,
    }}
  >
    <span style={{width: 12, height: 12, borderRadius: 12, backgroundColor: color, boxShadow: `0 0 18px ${color}`}} />
    {children}
  </div>
);

const Shell: React.FC<{children: React.ReactNode}> = ({children}) => (
  <AbsoluteFill style={{padding: '78px 92px 72px'}}>{children}</AbsoluteFill>
);

const Panel: React.FC<{
  children: React.ReactNode;
  delay?: number;
  style?: React.CSSProperties;
}> = ({children, delay = 0, style}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame: frame - delay, fps, config: {damping: 220}, durationInFrames: 26});
  return (
    <div
      style={{
        border: `1px solid ${palette.line}`,
        borderRadius: 12,
        background: palette.panel,
        boxShadow: '0 24px 70px rgba(0,0,0,0.28)',
        opacity: enter,
        transform: `translateY(${interpolate(enter, [0, 1], [34, 0])}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

const HeroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = fade(frame, 0, 20);
  const y = moveY(frame, 0, 38);

  return (
    <Shell>
      <div style={{opacity, transform: `translateY(${y}px)`}}>
        <Kicker>中文开发者教程</Kicker>
      </div>
      <div style={{display: 'grid', gridTemplateColumns: '1.04fr 0.96fr', gap: 44, alignItems: 'center', height: 850}}>
        <div style={{opacity, transform: `translateY(${y}px)`}}>
          <h1 style={{...sceneTitle, fontSize: 118}}>GAWorld</h1>
          <div style={{...sceneTitle, fontSize: 66, maxWidth: 880, marginTop: 18}}>
            把城市社会行为，做成可复现的多智能体实验场。
          </div>
          <div style={{...bodyText, marginTop: 28, maxWidth: 900}}>
            本教程面向开发社区：快速理解项目定位、核心能力、代码结构、主要接口，以及如何跑实验和扩展模块。
          </div>
        </div>
        <Panel delay={10} style={{padding: 26}}>
          <Img
            src={staticFile('gaworld-graphical-abstract.png')}
            style={{width: '100%', height: 474, objectFit: 'cover', borderRadius: 8}}
          />
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginTop: 18}}>
            {[
              ['城市', '地图与事件'],
              ['智能体', '画像与记忆'],
              ['对照', '实验与回放'],
            ].map(([title, desc], index) => (
              <div
                key={title}
                style={{
                  padding: '18px 16px',
                  borderRadius: 8,
                  background: 'rgba(255,255,255,0.04)',
                  border: `1px solid ${palette.line}`,
                }}
              >
                <div style={{fontFamily: titleFont, color: [palette.teal, palette.amber, palette.cyan][index], fontSize: 24, fontWeight: 750}}>
                  {title}
                </div>
                <div style={{fontFamily: titleFont, color: palette.muted, fontSize: 20, marginTop: 5}}>{desc}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </Shell>
  );
};

const loopItems = [
  ['感知', '读取画像、位置、环境事件、社交上下文', palette.teal],
  ['计划', '根据状态、需求、习惯生成日程与意图', palette.cyan],
  ['行动', '结合 LLM 推理、交通成本、经济约束执行动作', palette.amber],
  ['反思', '写入 episode、长期总结、关系与习惯变化', palette.coral],
] as const;

const LoopScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Shell>
      <div style={{opacity: fade(frame, 0, 18), transform: `translateY(${moveY(frame, 0, 28)}px)`}}>
        <Kicker color={palette.cyan}>核心仿真闭环</Kicker>
        <h2 style={{...sceneTitle, maxWidth: 980, marginTop: 24}}>每一天不是独立采样，而是会积累记忆、关系和行为惯性。</h2>
      </div>
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 22, marginTop: 54}}>
        {loopItems.map(([title, desc, color], index) => (
          <Panel key={title} delay={12 + index * 8} style={{padding: '28px 24px', minHeight: 250}}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 8,
                background: color,
                color: palette.ink,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: titleFont,
                fontSize: 28,
                fontWeight: 800,
              }}
            >
              {index + 1}
            </div>
            <div style={{fontFamily: titleFont, color: palette.paper, fontSize: 36, fontWeight: 750, marginTop: 24}}>{title}</div>
            <div style={{...bodyText, fontSize: 23, marginTop: 14}}>{desc}</div>
          </Panel>
        ))}
      </div>
      <div style={{position: 'absolute', left: 92, right: 92, bottom: 74, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 18}}>
        {['长期记忆', '动态行为', '经济状态', '位置轨迹'].map((item, index) => (
          <div
            key={item}
            style={{
              opacity: fade(frame, 58 + index * 8, 74 + index * 8),
              padding: '19px 22px',
              borderRadius: 8,
              border: `1px solid ${palette.line}`,
              background: 'rgba(7,16,22,0.58)',
              color: index % 2 === 0 ? palette.paper : palette.muted,
              fontFamily: titleFont,
              fontSize: 25,
              fontWeight: 700,
            }}
          >
            {item}
          </div>
        ))}
      </div>
    </Shell>
  );
};

const featureGroups = [
  ['数据启动', 'CSV 状态种子、Markdown 画像、城市地图', palette.green],
  ['LLM 路由', 'Ollama、OpenAI 兼容、Anthropic 兼容', palette.cyan],
  ['社会机制', '关系网络、偶遇链、习惯与承诺度', palette.teal],
  ['城市扰动', '天气、交通、政策、商业和新闻事件', palette.amber],
  ['对照实验', 'baseline 和 event 分支并行比较', palette.coral],
  ['本地工具', 'Dashboard、访谈 CLI、轨迹回放、报告', palette.violet],
] as const;

const FeatureScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Shell>
      <div style={{opacity: fade(frame, 0, 18), transform: `translateY(${moveY(frame, 0, 30)}px)`}}>
        <Kicker color={palette.amber}>主要功能</Kicker>
        <h2 style={{...sceneTitle, marginTop: 24, maxWidth: 1040}}>GAWorld 关注的是可控制、可回放、可对照的城市社会实验。</h2>
      </div>
      <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 22, marginTop: 46}}>
        {featureGroups.map(([title, desc, color], index) => (
          <Panel key={title} delay={10 + index * 6} style={{padding: 26, height: 186}}>
            <div style={{width: 42, height: 7, borderRadius: 7, background: color}} />
            <div style={{fontFamily: titleFont, color: palette.paper, fontSize: 32, fontWeight: 760, marginTop: 22}}>{title}</div>
            <div style={{...bodyText, fontSize: 22, marginTop: 10}}>{desc}</div>
          </Panel>
        ))}
      </div>
      <Panel delay={52} style={{position: 'absolute', left: 92, right: 92, bottom: 74, padding: '24px 30px'}}>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24, alignItems: 'center'}}>
          <div style={{fontFamily: titleFont, color: palette.paper, fontSize: 31, fontWeight: 750}}>推荐先跑的实验</div>
          <div style={{...bodyText, fontSize: 24}}>同一批 Agent，同一个随机种子，比较有事件和无事件两条分支。</div>
          <div style={{fontFamily: monoFont, color: '#d5fff0', fontSize: 22}}>compare-event --event-day 2 --seed 42</div>
        </div>
      </Panel>
    </Shell>
  );
};

const structure = [
  ['generative_city_sim.py', 'CLI 入口、主循环、仿真调度'],
  ['config.py', '兼容层，暴露 CONFIG'],
  ['gaworld/settings/', '配置拆分与 overrides 合并'],
  ['gaworld/core/', 'typed Agent 和 runner 抽象'],
  ['gaworld/io/', 'HTTP guard、网页提取、外部信息输入'],
  ['gaworld/work/', '真实任务队列、市场、适配器'],
  ['gaworld/apps/', 'dashboard、外部环境、relay 服务'],
  ['data/ 与 output/', '种子数据和运行产物'],
] as const;

const StructureScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Shell>
      <div style={{display: 'grid', gridTemplateColumns: '0.92fr 1.08fr', gap: 40}}>
        <div style={{opacity: fade(frame, 0, 18), transform: `translateY(${moveY(frame, 0, 28)}px)`}}>
          <Kicker color={palette.teal}>代码基本结构</Kicker>
          <h2 style={{...sceneTitle, marginTop: 24, maxWidth: 720}}>当前是从单文件模拟器向 package 结构迁移。</h2>
          <div style={{...bodyText, marginTop: 28}}>
            根目录模块保持兼容，新的跨模块代码优先进入 `gaworld/`。这让研究脚本可以继续跑，同时逐步沉淀稳定接口。
          </div>
        </div>
        <Panel delay={12} style={{padding: 26}}>
          <div style={{fontFamily: monoFont, color: palette.muted, fontSize: 22, marginBottom: 18}}>GAWorld/</div>
          {structure.map(([path, desc], index) => (
            <div
              key={path}
              style={{
                display: 'grid',
                gridTemplateColumns: '0.44fr 0.56fr',
                gap: 20,
                padding: '15px 0',
                borderTop: index === 0 ? 'none' : `1px solid ${palette.line}`,
                opacity: fade(frame, 18 + index * 5, 30 + index * 5),
              }}
            >
              <div style={{fontFamily: monoFont, color: index < 2 ? palette.amber : palette.cyan, fontSize: 23}}>{path}</div>
              <div style={{fontFamily: titleFont, color: palette.paper, fontSize: 24}}>{desc}</div>
            </div>
          ))}
        </Panel>
      </div>
    </Shell>
  );
};

const CommandLine: React.FC<{text: string; delay: number}> = ({text, delay}) => {
  const frame = useCurrentFrame();
  const reveal = Math.floor(interpolate(frame, [delay, delay + 22], [0, text.length], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }));
  return (
    <div style={{color: '#d5fff0', fontFamily: monoFont, fontSize: 25, lineHeight: 1.55}}>
      {text.slice(0, reveal)}
      {frame >= delay && reveal < text.length ? <span style={{opacity: frame % 16 < 8 ? 1 : 0}}>▌</span> : null}
    </div>
  );
};

const UsageScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Shell>
      <div style={{opacity: fade(frame, 0, 18), transform: `translateY(${moveY(frame, 0, 28)}px)`}}>
        <Kicker color={palette.coral}>接口与应用方法</Kicker>
        <h2 style={{...sceneTitle, marginTop: 24, maxWidth: 1050}}>先用 CLI 跑通，再从配置、数据和模块接口扩展。</h2>
      </div>
      <div style={{display: 'grid', gridTemplateColumns: '1.04fr 0.96fr', gap: 34, marginTop: 42}}>
        <Panel delay={10} style={{padding: 30, minHeight: 490, background: 'rgba(5,12,17,0.9)'}}>
          <div style={{display: 'flex', gap: 10, marginBottom: 22}}>
            {[palette.coral, palette.amber, palette.green].map((color) => (
              <span key={color} style={{width: 14, height: 14, borderRadius: 14, background: color}} />
            ))}
          </div>
          <CommandLine text="pip install -r requirements.txt" delay={18} />
          <CommandLine text="python generative_city_sim.py run" delay={46} />
          <CommandLine text="python generative_city_sim.py dashboard --port 8766" delay={74} />
          <CommandLine text={'python generative_city_sim.py interview --agent-id 31 --question "你今天为什么这样行动？"'} delay={104} />
          <CommandLine text="python generative_city_sim.py compare-event --event-day 2 --sim-days 3 --seed 42" delay={138} />
        </Panel>
        <div style={{display: 'grid', gap: 16}}>
          {[
            ['配置入口', '`gaworld/settings/*` 组合默认值，`GAWORLD_CONFIG_OVERRIDES` 覆盖运行参数。'],
            ['LLM 接口', '`llm_providers.call_llm` 负责 provider 路由、重试和 fallback。'],
            ['Agent 适配', '`gaworld.core.Agent` 在 legacy dict 上提供 typed accessor。'],
            ['输出接口', '`output/` 写入日志、记忆、状态 CSV、对照报告和可视化素材。'],
          ].map(([title, desc], index) => (
            <Panel key={title} delay={18 + index * 9} style={{padding: '23px 25px'}}>
              <div style={{fontFamily: titleFont, color: palette.paper, fontSize: 28, fontWeight: 760}}>{title}</div>
              <div style={{...bodyText, fontSize: 21, marginTop: 8}}>{desc}</div>
            </Panel>
          ))}
        </div>
      </div>
    </Shell>
  );
};

const OutputScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Shell>
      <div style={{opacity: fade(frame, 0, 18), transform: `translateY(${moveY(frame, 0, 28)}px)`}}>
        <Kicker color={palette.violet}>面向社区的扩展路径</Kicker>
        <h2 style={{...sceneTitle, marginTop: 24, maxWidth: 1040}}>从一个可运行实验开始，逐步贡献新的机制、适配器和评估指标。</h2>
      </div>
      <Window src="social-network.png" title="关系网络" desc="观察社交结构变化" x={92} y={280} width={500} height={360} delay={16} />
      <Window src="agent-state-over-time.png" title="状态轨迹" desc="比较行为和心理状态" x={530} y={245} width={690} height={410} delay={26} />
      <Window src="gaworld-graphical-abstract.png" title="实验框架" desc="把机制接入闭环" x={1168} y={280} width={660} height={360} delay={36} />
      <div style={{position: 'absolute', left: 92, right: 92, bottom: 70, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 18}}>
        {['新增环境事件', '扩展城市地图', '接入新 LLM provider', '添加评估指标'].map((item, index) => (
          <Panel key={item} delay={52 + index * 6} style={{padding: '20px 22px', textAlign: 'center'}}>
            <div style={{fontFamily: titleFont, color: palette.paper, fontSize: 25, fontWeight: 760}}>{item}</div>
          </Panel>
        ))}
      </div>
    </Shell>
  );
};

const Window: React.FC<{
  src: string;
  title: string;
  desc: string;
  x: number;
  y: number;
  width: number;
  height: number;
  delay: number;
}> = ({src, title, desc, x, y, width, height, delay}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame: frame - delay, fps, config: {damping: 220}, durationInFrames: 30});
  const float = Math.sin((frame + delay) / 34) * 7;
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width,
        height,
        borderRadius: 12,
        overflow: 'hidden',
        border: `1px solid ${palette.line}`,
        background: palette.panel,
        opacity: enter,
        transform: `translateY(${interpolate(enter, [0, 1], [38, float])}px)`,
        boxShadow: '0 24px 70px rgba(0,0,0,0.32)',
      }}
    >
      <div style={{display: 'flex', justifyContent: 'space-between', padding: '16px 20px', borderBottom: `1px solid ${palette.line}`}}>
        <div style={{fontFamily: titleFont, color: palette.paper, fontSize: 23, fontWeight: 760}}>{title}</div>
        <div style={{fontFamily: titleFont, color: palette.muted, fontSize: 18}}>{desc}</div>
      </div>
      <Img src={staticFile(src)} style={{width: '100%', height: height - 59, objectFit: 'cover'}} />
    </div>
  );
};

export const GAWorldTutorialCN: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: palette.ink}}>
      <Background />
      <Sequence from={0} durationInFrames={210} premountFor={30}>
        <HeroScene />
      </Sequence>
      <Sequence from={180} durationInFrames={230} premountFor={30}>
        <LoopScene />
      </Sequence>
      <Sequence from={390} durationInFrames={230} premountFor={30}>
        <FeatureScene />
      </Sequence>
      <Sequence from={600} durationInFrames={240} premountFor={30}>
        <StructureScene />
      </Sequence>
      <Sequence from={820} durationInFrames={260} premountFor={30}>
        <UsageScene />
      </Sequence>
      <Sequence from={1060} durationInFrames={240} premountFor={30}>
        <OutputScene />
      </Sequence>
    </AbsoluteFill>
  );
};
