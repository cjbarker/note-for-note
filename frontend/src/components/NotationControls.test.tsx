import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import NotationControls from "./NotationControls";
import * as api from "../api";

vi.mock("../api", () => ({ renotate: vi.fn() }));

const stats = {
  note_count: 3,
  duration_seconds: 2,
  tempo_bpm: 120,
  time_signature: "4/4",
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("NotationControls", () => {
  it("debounces a single renotate call when the tempo changes", async () => {
    const result = {
      musicXml: "<score/>",
      midiBase64: "re-timed",
      stats: { ...stats, tempo_bpm: 90 },
    };
    vi.mocked(api.renotate).mockResolvedValue(result);
    const onRenotated = vi.fn();

    render(<NotationControls midiBase64="abc" stats={stats} onRenotated={onRenotated} />);

    // No call should fire on mount (controls match the current stats).
    expect(api.renotate).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "90" } });

    // Still debounced — nothing before the timer elapses.
    expect(api.renotate).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(api.renotate).toHaveBeenCalledTimes(1);
    expect(api.renotate).toHaveBeenCalledWith("abc", 90, "4/4", 60);
    expect(onRenotated).toHaveBeenCalledWith(result.musicXml, result.stats, result.midiBase64, 60);
  });

  it("sends the split point when it changes", async () => {
    const result = {
      musicXml: "<score/>",
      midiBase64: "re-timed",
      stats: { ...stats, tempo_bpm: 120, time_signature: "4/4" },
    };
    vi.mocked(api.renotate).mockResolvedValue(result);
    const onRenotated = vi.fn();

    render(<NotationControls midiBase64="abc" stats={stats} onRenotated={onRenotated} />);

    // Change the split point slider.
    fireEvent.change(screen.getByRole("slider"), { target: { value: "72" } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });

    expect(api.renotate).toHaveBeenCalledTimes(1);
    expect(api.renotate).toHaveBeenCalledWith("abc", 120, "4/4", 72);
  });
});
