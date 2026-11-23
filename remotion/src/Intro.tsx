import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { FONT } from "./fonts";

export type IntroProps = {
  readonly seriesTitle: string;
  readonly episodeLabel: string;
  readonly episodeTitle: string;
};

// 3-second animated title sting played before every episode.
export const Intro: React.FC<IntroProps> = ({ seriesTitle, episodeLabel, episodeTitle }) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const vertical = height > width;
  const unit = Math.min(width, height) / 1080;

  const beamAngle = interpolate(frame, [0, durationInFrames], [-70, 40]);
  const titleIn = spring({ frame: frame - 6, fps, config: { damping: 14 } });
  const subIn = spring({ frame: frame - 22, fps, config: { damping: 16 } });
  const fadeOut = interpolate(frame, [durationInFrames - 10, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: "radial-gradient(circle at 50% 120%, #2f3f70 0%, #121c42 45%, #070b1f 100%)", opacity: fadeOut }}>
      {/* sweeping lighthouse beam */}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end" }}>
        <div
          style={{
            position: "absolute",
            bottom: height * 0.18,
            left: width / 2,
            width: Math.max(width, height) * 1.4,
            height: 220 * unit,
            transformOrigin: "0% 50%",
            transform: `translateY(50%) rotate(${beamAngle - 90}deg)`,
            background: "linear-gradient(90deg, rgba(255,246,200,0.55), rgba(255,246,200,0))",
            clipPath: "polygon(0 45%, 100% 0, 100% 100%, 0 55%)",
          }}
        />
        <div style={{ width: 70 * unit, height: height * 0.18, marginBottom: 0, background: "repeating-linear-gradient(#f4f1ea 0 22%, #c8382f 22% 44%)", borderRadius: `${12 * unit}px ${12 * unit}px 0 0` }} />
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", fontFamily: FONT, textAlign: "center", padding: 60 * unit }}>
        <div style={{ color: "#ffd84a", fontWeight: 700, fontSize: (vertical ? 96 : 120) * unit, transform: `scale(${0.6 + 0.4 * titleIn})`, opacity: titleIn, textShadow: "0 8px 30px rgba(0,0,0,0.6)" }}>
          {seriesTitle}
        </div>
        <div style={{ marginTop: 28 * unit, color: "#ffffff", fontSize: 46 * unit, opacity: subIn, transform: `translateY(${(1 - subIn) * 40}px)` }}>
          <span style={{ background: "#c8382f", padding: `${6 * unit}px ${18 * unit}px`, borderRadius: 12 * unit, fontWeight: 700 }}>{episodeLabel}</span>
          <div style={{ marginTop: 18 * unit, fontSize: 54 * unit, fontWeight: 700 }}>{episodeTitle}</div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
