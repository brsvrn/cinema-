import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

export const FONT = "StudioSans";

// DejaVu Sans covers all Turkish glyphs (ç ğ ı İ ö ş ü).
export const fontsLoaded = Promise.all([
  loadFont({ family: FONT, url: staticFile("fonts/DejaVuSans.ttf"), weight: "400" }),
  loadFont({ family: FONT, url: staticFile("fonts/DejaVuSans-Bold.ttf"), weight: "700" }),
]);
