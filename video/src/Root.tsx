import {Composition} from 'remotion';
import {GAWorldIntro} from './GAWorldIntro';

export const RemotionRoot = () => {
  return (
    <Composition
      id="GAWorldIntro"
      component={GAWorldIntro}
      durationInFrames={660}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
