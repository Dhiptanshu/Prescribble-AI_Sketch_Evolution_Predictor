import type { Prediction } from "@prescribble/engine";
import type { RefObject, ReactNode } from "react";
import type { BoardHandle } from "../../../components/DrawingBoard";

/** What the Studio gives each mode panel. */
export interface ModeContext {
  classes: string[];
  last: Prediction | null;
  boardRef: RefObject<BoardHandle>;
  /** Run the model on a drawing and wait for that exact result (used by scripted playback). */
  predictNow: (strokes: import("@prescribble/engine").Stroke[], record?: boolean) => Promise<Prediction | null>;
  setLocked: (v: boolean) => void;
  setBanner: (v: ReactNode) => void;
  setTruth: (v: string | null) => void;
  setProgress: (v: number | undefined) => void;
}
