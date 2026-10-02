import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { SketchModel } from "@prescribble/engine";

export const MODEL_VERSION = "v1";

export type EngineState =
  | { status: "loading" }
  | { status: "ready"; model: SketchModel }
  | { status: "error"; message: string };

const EngineContext = createContext<EngineState>({ status: "loading" });

/** Loads the ONNX model once, in the browser. Everything (Studio, challenges, replay) shares it. */
export function EngineProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EngineState>({ status: "loading" });
  useEffect(() => {
    let cancelled = false;
    const base = import.meta.env.BASE_URL;
    SketchModel.load({ modelBase: `${base}models/${MODEL_VERSION}/`, wasmBase: `${base}ort/` })
      .then((model) => !cancelled && setState({ status: "ready", model }))
      .catch((e) => !cancelled && setState({ status: "error", message: e instanceof Error ? e.message : String(e) }));
    return () => { cancelled = true; };
  }, []);
  return <EngineContext.Provider value={state}>{children}</EngineContext.Provider>;
}

export const useEngine = () => useContext(EngineContext);
