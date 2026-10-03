import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { SketchModel } from "@prescribble/engine";
import { liveVersion } from "./version";

export type EngineState =
  | { status: "loading" }
  | { status: "ready"; model: SketchModel; version: string }
  | { status: "error"; message: string };

const EngineContext = createContext<EngineState>({ status: "loading" });

/** Loads the ONNX model once, in the browser. Everything (Studio, challenges, replay) shares it. */
export function EngineProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EngineState>({ status: "loading" });
  useEffect(() => {
    let cancelled = false;
    const base = import.meta.env.BASE_URL;
    liveVersion(base)
      .then(async (version) => ({ version, model: await SketchModel.load({ modelBase: `${base}models/${version}/`, wasmBase: `${base}ort/` }) }))
      .then(({ model, version }) => !cancelled && setState({ status: "ready", model, version }))
      .catch((e) => !cancelled && setState({ status: "error", message: e instanceof Error ? e.message : String(e) }));
    return () => { cancelled = true; };
  }, []);
  return <EngineContext.Provider value={state}>{children}</EngineContext.Provider>;
}

export const useEngine = () => useContext(EngineContext);
