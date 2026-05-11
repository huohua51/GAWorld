import {Composition} from 'remotion';
import {GAWorldIntro} from './GAWorldIntro';
import {GAWorldTutorialCN} from './GAWorldTutorialCN';

export const RemotionRoot = () => {
  return (
    <>
      <Composition
        id="GAWorldIntro"
        component={GAWorldIntro}
        durationInFrames={660}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="GAWorldTutorialCN"
        component={GAWorldTutorialCN}
        durationInFrames={1300}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
