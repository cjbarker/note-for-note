// Type declarations for `html-midi-player`, which ships no types and registers
// two custom elements (<midi-player>, <midi-visualizer>) as an import side-effect.
import type { DetailedHTMLProps, HTMLAttributes } from "react";

declare module "html-midi-player" {
  export class PlayerElement extends HTMLElement {
    src: string | null;
    soundFont: string | null;
    addVisualizer(visualizer: HTMLElement): void;
  }
  export class VisualizerElement extends HTMLElement {
    src: string | null;
  }
}

type MidiPlayerProps = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  src?: string;
  /** "" → default sampled SoundFont; omit/null → oscillator synth. */
  "sound-font"?: string;
  loop?: boolean;
  /** CSS selector matching <midi-visualizer> elements to bind. */
  visualizer?: string;
};

type MidiVisualizerProps = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  src?: string;
  type?: "piano-roll" | "waterfall" | "staff";
};

declare global {
  namespace JSX {
    interface IntrinsicElements {
      "midi-player": MidiPlayerProps;
      "midi-visualizer": MidiVisualizerProps;
    }
  }
}
