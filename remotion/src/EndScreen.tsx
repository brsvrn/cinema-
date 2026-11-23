import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { FONT } from "./fonts";

export type EndScreenProps = {
  readonly seriesTitle: string;
  readonly nextTitle: string;
  readonly backgroundImage: string; // file in public/ (e.g. episode thumbnail frame)
};

// 10-second YouTube end screen. The two empty boxes are where YouTube's end-screen
// elements ("next video" + "subscribe") are placed in YouTube Studio.
export const EndScreen: React.FC<EndScreenProps> = ({ seriesTitle, nextTitle, backgroundImage }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const unit = height / 1080;
  const appear = spring({ frame, fps, config: { damping: 18 } });
  const pulse = 1 + 0.04 * Math.sin((frame / fps) * Math.PI * 2);
  const zoom = interpolate(frame, [0, 10 * fps], [1.05, 1.15]);

  return (
    <AbsoluteFill style={{ background: "#0f1117", fontFamily: FONT }}>
      {backgroundImage ? (
        <Img src={staticFile(backgroundImage)} style={{ width, height, objectFit: "cover", transform: `scale(${zoom})`, filter: "blur(14px) brightness(0.45)" }} />
      ) : null}
      <AbsoluteFill style={{ padding: 80 * unit, color: "#fff" }}>
        <div style={{ fontSize: 64 * unit, fontWeight: 700, color: "#ffd84a", opacity: appear }}>{seriesTitle}</div>
        <div style={{ fontSize: 40 * unit, marginTop: 12 * unit, opacity: appear }}>Devam edecek…</div>
        <div style={{ display: "flex", gap: 80 * unit, marginTop: 90 * unit, alignItems: "center", transform: `translateY(${(1 - appear) * 60}px)`, opacity: appear }}>
          <div style={{ width: 880 * unit, height: 495 * unit, border: `${6 * unit}px dashed rgba(255,255,255,0.75)`, borderRadius: 24 * unit, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.35)" }}>
            <div style={{ fontSize: 36 * unit, opacity: 0.85 }}>Sonraki bölüm</div>
            <div style={{ fontSize: 56 * unit, fontWeight: 700, marginTop: 12 * unit, textAlign: "center", padding: `0 ${30 * unit}px` }}>{nextTitle}</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 28 * unit }}>
            <div style={{ width: 330 * unit, height: 330 * unit, borderRadius: "50%", border: `${6 * unit}px dashed rgba(255,255,255,0.75)`, transform: `scale(${pulse})` }} />
            <div style={{ background: "#c8382f", padding: `${16 * unit}px ${40 * unit}px`, borderRadius: 16 * unit, fontSize: 44 * unit, fontWeight: 700 }}>ABONE OL</div>
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
