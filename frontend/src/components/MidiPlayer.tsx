// In-browser audio playback of the transcribed MIDI, so the user can *listen*
// to the result and judge the transcription quality by ear.
//
// Built on the html-midi-player web component (importing it registers the
// <midi-player> / <midi-visualizer> custom elements). It plays the same base64
// MIDI the backend already returns, with a sampled acoustic-piano SoundFont
// (sound-font="" → the library's default sgm_plus, loaded lazily on first Play),
// plus a piano-roll that shows what's playing.
import { useEffect, useRef } from "react";
import "html-midi-player";

interface Props {
  midiBase64: string;
}

const VISUALIZER_ID = "nfn-midi-visualizer";

export default function MidiPlayer({ midiBase64 }: Props) {
  const playerRef = useRef<HTMLElement>(null);
  const src = `data:audio/midi;base64,${midiBase64}`;

  // Bind the visualizer to the player after both have mounted. Setting the
  // `visualizer` attribute here (rather than in JSX) avoids a render-order race
  // where the player could evaluate the selector before the visualizer exists.
  useEffect(() => {
    playerRef.current?.setAttribute("visualizer", `#${VISUALIZER_ID}`);
  }, []);

  return (
    <div className="midi-player">
      <midi-player ref={playerRef} src={src} sound-font="" />
      <midi-visualizer id={VISUALIZER_ID} type="piano-roll" src={src} />
    </div>
  );
}
