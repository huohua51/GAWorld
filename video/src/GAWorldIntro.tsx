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
  bg: '#09131a',
  teal: '#1cc8a0',
  cyan: '#56d4ff',
  orange: '#ff9a4d',
  cream: '#f7f3ea',
  mist: '#b6c8cf',
  panel: 'rgba(10, 20, 28, 0.72)',
  line: 'rgba(156, 215, 230, 0.18)',
};

const titleFont = '"Avenir Next", "Helvetica Neue", sans-serif';
const bodyFont = '"Avenir Next", "Segoe UI", sans-serif';

const fullSize: React.CSSProperties = {
  width: '100%',
  height: '100%',
};

const sceneTitleStyle: React.CSSProperties = {
  fontFamily: titleFont,
  fontSize: 76,
  fontWeight: 700,
  lineHeight: 1,
  letterSpacing: -2.5,
  color: palette.cream,
  margin: 0,
};

const bodyTextStyle: React.CSSProperties = {
  fontFamily: bodyFont,
  color: palette.mist,
  fontSize: 28,
  lineHeight: 1.5,
};

const fade = (frame: number, start: number, end: number) =>
  interpolate(frame, [start, end], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

const slideUp = (frame: number, start: number, distance: number) =>
  interpolate(frame, [start, start + 18], [distance, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

const GridBackdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const drift = (frame * 0.4) % 90;
  const pulse = 0.3 + spring({frame, fps: 30, config: {damping: 200}}) * 0.2;

  return (
    <AbsoluteFill
      style={{
        background: `
          radial-gradient(circle at 18% 18%, rgba(28, 200, 160, 0.24), transparent 32%),
          radial-gradient(circle at 80% 20%, rgba(86, 212, 255, 0.18), transparent 28%),
          radial-gradient(circle at 50% 82%, rgba(255, 154, 77, 0.16), transparent 30%),
          linear-gradient(180deg, #0b1720 0%, #081017 55%, #060d13 100%)
        `,
      }}
    >
      <svg style={fullSize} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <pattern
            id="grid"
            width="90"
            height="90"
            patternUnits="userSpaceOnUse"
            patternTransform={`translate(${drift} ${drift * 0.6})`}
          >
            <path
              d="M 90 0 L 0 0 0 90"
              fill="none"
              stroke="rgba(120, 193, 210, 0.12)"
              strokeWidth="1"
            />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#grid)" />
        {[0, 1, 2].map((index) => {
          const radius = 160 + index * 140 + frame * (0.5 + index * 0.15);
          return (
            <circle
              key={index}
              cx={width * 0.76}
              cy={height * 0.28}
              r={radius}
              fill="none"
              stroke={`rgba(86, 212, 255, ${0.12 - index * 0.025})`}
              strokeWidth={2}
            />
          );
        })}
        <circle
          cx={width * 0.76}
          cy={height * 0.28}
          r={22 + pulse * 18}
          fill="rgba(86, 212, 255, 0.22)"
          stroke="rgba(86, 212, 255, 0.9)"
          strokeWidth={2}
        />
      </svg>
    </AbsoluteFill>
  );
};

const Kicker: React.FC<{text: string; color?: string}> = ({text, color = palette.teal}) => (
  <div
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 14,
      padding: '14px 20px',
      borderRadius: 999,
      border: `1px solid ${palette.line}`,
      color,
      backgroundColor: 'rgba(8, 18, 24, 0.58)',
      fontFamily: bodyFont,
      fontWeight: 700,
      letterSpacing: '0.18em',
      textTransform: 'uppercase',
      fontSize: 17,
    }}
  >
    <span
      style={{
        width: 12,
        height: 12,
        borderRadius: 999,
        backgroundColor: color,
        boxShadow: `0 0 20px ${color}`,
      }}
    />
    {text}
  </div>
);

const MetricChip: React.FC<{label: string; value: string; delay: number}> = ({
  label,
  value,
  delay,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = spring({
    frame: frame - delay,
    fps,
    config: {damping: 200},
    durationInFrames: 24,
  });

  return (
    <div
      style={{
        width: 256,
        padding: '24px 28px',
        borderRadius: 28,
        border: `1px solid ${palette.line}`,
        background: 'rgba(8, 18, 24, 0.64)',
        backdropFilter: 'blur(12px)',
        transform: `translateY(${interpolate(progress, [0, 1], [40, 0])}px) scale(${interpolate(
          progress,
          [0, 1],
          [0.94, 1],
        )})`,
        opacity: progress,
      }}
    >
      <div
        style={{
          fontFamily: bodyFont,
          fontSize: 17,
          color: palette.mist,
          textTransform: 'uppercase',
          letterSpacing: '0.12em',
        }}
      >
        {label}
      </div>
      <div
        style={{
          marginTop: 10,
          color: palette.cream,
          fontFamily: titleFont,
          fontWeight: 700,
          fontSize: 50,
          letterSpacing: -1.4,
        }}
      >
        {value}
      </div>
    </div>
  );
};

const LoopCard: React.FC<{
  title: string;
  subtitle: string;
  accent: string;
  index: number;
}> = ({title, subtitle, accent, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = spring({
    frame: frame - index * 7,
    fps,
    config: {damping: 200},
    durationInFrames: 26,
  });

  return (
    <div
      style={{
        padding: '28px 26px',
        borderRadius: 28,
        background: 'rgba(8, 18, 24, 0.72)',
        border: `1px solid ${palette.line}`,
        boxShadow: `0 18px 50px rgba(0, 0, 0, 0.22)`,
        transform: `translateY(${interpolate(progress, [0, 1], [50, 0])}px)`,
        opacity: progress,
      }}
    >
      <div
        style={{
          width: 54,
          height: 54,
          borderRadius: 18,
          background: `linear-gradient(135deg, ${accent}, rgba(255,255,255,0.08))`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#041016',
          fontSize: 26,
          fontWeight: 700,
          fontFamily: titleFont,
        }}
      >
        {index + 1}
      </div>
      <div
        style={{
          marginTop: 22,
          fontFamily: titleFont,
          fontWeight: 700,
          fontSize: 34,
          color: palette.cream,
        }}
      >
        {title}
      </div>
      <div style={{...bodyTextStyle, fontSize: 22, marginTop: 12}}>{subtitle}</div>
    </div>
  );
};

const WindowFrame: React.FC<{
  src: string;
  title: string;
  subtitle: string;
  x: number;
  y: number;
  width: number;
  height: number;
  delay: number;
}> = ({src, title, subtitle, x, y, width, height, delay}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const entrance = spring({
    frame: frame - delay,
    fps,
    config: {damping: 200},
    durationInFrames: 30,
  });
  const float = Math.sin((frame + delay * 3) / 28) * 8;

  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width,
        height,
        borderRadius: 30,
        overflow: 'hidden',
        border: `1px solid ${palette.line}`,
        background: 'rgba(8, 18, 24, 0.72)',
        boxShadow: '0 22px 80px rgba(0, 0, 0, 0.34)',
        transform: `translateY(${interpolate(entrance, [0, 1], [55, float])}px) scale(${interpolate(
          entrance,
          [0, 1],
          [0.94, 1],
        )})`,
        opacity: entrance,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '18px 22px',
          borderBottom: `1px solid ${palette.line}`,
          background: 'rgba(255,255,255,0.02)',
        }}
      >
        <div style={{fontFamily: titleFont, fontSize: 24, color: palette.cream}}>{title}</div>
        <div style={{fontFamily: bodyFont, fontSize: 16, color: palette.mist}}>{subtitle}</div>
      </div>
      <div style={{padding: 18}}>
        <Img
          src={staticFile(src)}
          style={{
            width: '100%',
            height: height - 86,
            objectFit: 'cover',
            borderRadius: 18,
          }}
        />
      </div>
    </div>
  );
};

const CommandBlock: React.FC = () => {
  const frame = useCurrentFrame();
  const reveal = Math.floor(interpolate(frame, [10, 78], [0, 214], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }));
  const command = [
    'python generative_city_sim.py compare-event \\',
    '  --event-name "临时交通限行" \\',
    '  --event-day 2 --event-time 09:00 \\',
    '  --sim-days 3 --seed 42',
  ].join('\n');

  return (
    <div
      style={{
        padding: '28px 32px',
        borderRadius: 30,
        background: 'rgba(6, 14, 19, 0.9)',
        border: '1px solid rgba(28, 200, 160, 0.18)',
        boxShadow: '0 30px 90px rgba(0, 0, 0, 0.3)',
      }}
    >
      <div
        style={{
          display: 'flex',
          gap: 10,
          marginBottom: 22,
        }}
      >
        {['#ff6b6b', '#ffcf5a', '#42d392'].map((color) => (
          <span
            key={color}
            style={{
              width: 14,
              height: 14,
              borderRadius: 999,
              backgroundColor: color,
            }}
          />
        ))}
      </div>
      <pre
        style={{
          margin: 0,
          whiteSpace: 'pre-wrap',
          fontFamily: '"SFMono-Regular", "Menlo", monospace',
          fontSize: 30,
          lineHeight: 1.55,
          color: '#cff5e6',
        }}
      >
        {command.slice(0, reveal)}
        <span
          style={{
            opacity: frame % 20 < 10 ? 1 : 0,
          }}
        >
          |
        </span>
      </pre>
    </div>
  );
};

const StepRail: React.FC = () => {
  const frame = useCurrentFrame();
  const steps = [
    ['Reset state', 'Isolate event and baseline runs'],
    ['Parallel branches', 'Same agents, same seed, changed condition'],
    ['Aggregate deltas', 'Metrics, summaries, episodic traces'],
  ] as const;

  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
      {steps.map(([title, subtitle], index) => {
        const start = 30 + index * 14;
        const opacity = fade(frame, start, start + 16);
        const x = slideUp(frame, start, 34);
        return (
          <div
            key={title}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 22,
              padding: '22px 24px',
              borderRadius: 26,
              background: 'rgba(8, 18, 24, 0.64)',
              border: `1px solid ${palette.line}`,
              opacity,
              transform: `translateY(${x}px)`,
            }}
          >
            <div
              style={{
                width: 54,
                height: 54,
                borderRadius: 18,
                backgroundColor: index === 1 ? palette.cyan : index === 2 ? palette.orange : palette.teal,
                color: '#051017',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: titleFont,
                fontWeight: 700,
                fontSize: 24,
              }}
            >
              {index + 1}
            </div>
            <div>
              <div
                style={{
                  fontFamily: titleFont,
                  fontSize: 28,
                  color: palette.cream,
                  fontWeight: 700,
                }}
              >
                {title}
              </div>
              <div style={{...bodyTextStyle, fontSize: 20, marginTop: 6}}>{subtitle}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export const GAWorldIntro: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: palette.bg}}>
      <GridBackdrop />

      <Sequence from={0} durationInFrames={210} premountFor={30}>
        <HeroScene />
      </Sequence>

      <Sequence from={150} durationInFrames={230} premountFor={30}>
        <LoopScene />
      </Sequence>

      <Sequence from={340} durationInFrames={190} premountFor={30}>
        <CompareScene />
      </Sequence>

      <Sequence from={470} durationInFrames={190} premountFor={30}>
        <OutputsScene />
      </Sequence>
    </AbsoluteFill>
  );
};

const HeroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = fade(frame, 0, 20);
  const y = slideUp(frame, 0, 40);

  return (
    <AbsoluteFill style={{padding: '86px 96px 70px'}}>
      <div style={{opacity, transform: `translateY(${y}px)`}}>
        <Kicker text="Generative Agent Simulation" />
      </div>

      <div
        style={{
          marginTop: 40,
          display: 'grid',
          gridTemplateColumns: '1.16fr 0.84fr',
          gap: 34,
          alignItems: 'end',
        }}
      >
        <div style={{opacity, transform: `translateY(${y}px)`}}>
          <h1 style={{...sceneTitleStyle, fontSize: 118, maxWidth: 9.5 * 100}}>
            GAWorld
          </h1>
          <div
            style={{
              ...sceneTitleStyle,
              marginTop: 16,
              maxWidth: 950,
              fontSize: 72,
              lineHeight: 1.08,
            }}
          >
            Turn urban policy discussion into a replayable social experiment.
          </div>
          <div style={{...bodyTextStyle, marginTop: 28, maxWidth: 860}}>
            GAWorld combines profile-driven agents, environment shocks, social network
            dynamics, long-term memory, and event comparison into one city-scale simulator.
          </div>
        </div>

        <div
          style={{
            justifySelf: 'stretch',
            padding: '30px 30px 32px',
            borderRadius: 34,
            border: `1px solid ${palette.line}`,
            background: 'rgba(8, 18, 24, 0.66)',
            boxShadow: '0 30px 90px rgba(0,0,0,0.28)',
            opacity: fade(frame, 8, 28),
            transform: `translateY(${slideUp(frame, 8, 50)}px)`,
          }}
        >
          <div style={{display: 'flex', flexDirection: 'column', gap: 16}}>
            <MetricChip label="Seed Agents" value="53" delay={18} />
            <MetricChip label="Core Loop" value="4-step" delay={26} />
            <MetricChip label="Focus" value="Counterfactuals" delay={34} />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const LoopScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{padding: '96px 92px'}}>
      <div style={{opacity: fade(frame, 0, 18), transform: `translateY(${slideUp(frame, 0, 32)}px)`}}>
        <Kicker text="Daily Agent Loop" color={palette.cyan} />
        <div style={{...sceneTitleStyle, marginTop: 24, maxWidth: 960}}>
          Each simulated day compounds memory, habits, and social change.
        </div>
      </div>

      <div
        style={{
          marginTop: 44,
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 22,
        }}
      >
        <LoopCard
          title="Perception"
          subtitle="Agents read context, location, events, and nearby social signals."
          accent={palette.teal}
          index={0}
        />
        <LoopCard
          title="Planning"
          subtitle="Short-horizon intent is generated from state, profile, and current pressures."
          accent={palette.cyan}
          index={1}
        />
        <LoopCard
          title="Action"
          subtitle="Choices blend LLM reasoning with habit bias, mobility, and time-aware routing."
          accent={palette.orange}
          index={2}
        />
        <LoopCard
          title="Reflection"
          subtitle="Episodes, summaries, relationships, and routines are updated across days."
          accent="#ffd26a"
          index={3}
        />
      </div>

      <div
        style={{
          position: 'absolute',
          left: 92,
          right: 92,
          bottom: 94,
          display: 'flex',
          gap: 18,
          opacity: fade(frame, 44, 66),
        }}
      >
        {['Memory persistence', 'Habit formation', 'Relationship drift', 'Location-aware actions'].map(
          (label, index) => (
            <div
              key={label}
              style={{
                flex: 1,
                padding: '20px 22px',
                borderRadius: 22,
                border: `1px solid ${palette.line}`,
                background: 'rgba(8, 18, 24, 0.54)',
                color: index % 2 === 0 ? palette.cream : palette.mist,
                fontFamily: bodyFont,
                fontWeight: 600,
                fontSize: 24,
              }}
            >
              {label}
            </div>
          ),
        )}
      </div>
    </AbsoluteFill>
  );
};

const CompareScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{padding: '90px 92px'}}>
      <div style={{display: 'grid', gridTemplateColumns: '1.05fr 0.95fr', gap: 34}}>
        <div>
          <div style={{opacity: fade(frame, 0, 16), transform: `translateY(${slideUp(frame, 0, 28)}px)`}}>
            <Kicker text="Counterfactual Workflow" color={palette.orange} />
            <div style={{...sceneTitleStyle, marginTop: 24, maxWidth: 840}}>
              One command generates an event branch, a baseline branch, and a comparable record.
            </div>
          </div>
          <div style={{marginTop: 34, opacity: fade(frame, 10, 26)}}>
            <CommandBlock />
          </div>
        </div>
        <div style={{paddingTop: 106}}>
          <StepRail />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const OutputsScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{padding: '84px 92px'}}>
      <div style={{opacity: fade(frame, 0, 16), transform: `translateY(${slideUp(frame, 0, 24)}px)`}}>
        <Kicker text="Evidence And Playback" />
        <div style={{...sceneTitleStyle, marginTop: 24, maxWidth: 960}}>
          The simulator produces visuals, traces, and reports that are ready for demos or research reviews.
        </div>
      </div>

      <WindowFrame
        src="gaworld-graphical-abstract.png"
        title="System overview"
        subtitle="Research framing"
        x={92}
        y={250}
        width={760}
        height={450}
        delay={10}
      />
      <WindowFrame
        src="social-network.png"
        title="Social network"
        subtitle="Relationship structure"
        x={760}
        y={220}
        width={460}
        height={440}
        delay={20}
      />
      <WindowFrame
        src="agent-state-over-time.png"
        title="State trajectories"
        subtitle="Time-series output"
        x={1188}
        y={250}
        width={640}
        height={450}
        delay={30}
      />

      <div
        style={{
          position: 'absolute',
          left: 92,
          right: 92,
          bottom: 80,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          opacity: fade(frame, 42, 60),
        }}
      >
        <div style={{...bodyTextStyle, fontSize: 26, maxWidth: 840}}>
          Logs, episodic memory, comparison summaries, state history, and map playback all
          live in generated outputs that can be replayed or inspected after the run.
        </div>
        <div
          style={{
            fontFamily: titleFont,
            fontWeight: 700,
            fontSize: 38,
            color: palette.cream,
            textAlign: 'right',
          }}
        >
          Build policy experiments.
          <br />
          Rewind agent society.
        </div>
      </div>
    </AbsoluteFill>
  );
};
