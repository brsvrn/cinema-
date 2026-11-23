import React from "react";
import { Composition } from "remotion";
import { EndScreen } from "./EndScreen";
import { fontsLoaded } from "./fonts";
import { Intro } from "./Intro";

// Packaging layer for episodes rendered by the Python worker.
// The worker renders these short clips and concatenates them around the episode with FFmpeg,
// so the long episode itself is never re-rendered through the browser.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Intro"
        component={Intro}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ seriesTitle: "Fener Bekçileri", episodeLabel: "Bölüm 3", episodeTitle: "Kırmızı Yelkenli" }}
        calculateMetadata={async () => {
          await fontsLoaded;
          return {};
        }}
      />
      <Composition
        id="IntroVertical"
        component={Intro}
        durationInFrames={60}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ seriesTitle: "Fener Bekçileri", episodeLabel: "Bölüm 3", episodeTitle: "Kırmızı Yelkenli" }}
        calculateMetadata={async () => {
          await fontsLoaded;
          return {};
        }}
      />
      <Composition
        id="EndScreen"
        component={EndScreen}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ seriesTitle: "Fener Bekçileri", nextTitle: "Bölüm 4: Yakamoz Koyu", backgroundImage: "" }}
        calculateMetadata={async () => {
          await fontsLoaded;
          return {};
        }}
      />
    </>
  );
};
