import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { LoginPage, RegisterPage } from "./features/auth/AuthPages";
import { DrawingPage } from "./features/gallery/DrawingPage";
import { GalleryPage } from "./features/gallery/GalleryPage";
import { LandingPage } from "./features/landing/LandingPage";
import { SharedPage } from "./features/share/SharedPage";
import { StatsPage } from "./features/stats/StatsPage";
import { StudioPage } from "./features/studio/StudioPage";
import { AuthProvider } from "./lib/auth";
import { EngineProvider } from "./lib/engine";

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

function NotFound() {
  return <div className="auth-wrap card"><h1>Page not found</h1><p className="sub">That page does not exist.</p><Link className="btn primary" to="/">Go home</Link></div>;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <EngineProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<LandingPage />} />
                <Route path="studio" element={<StudioPage />} />
                <Route path="gallery" element={<RequireAuth><GalleryPage /></RequireAuth>} />
                <Route path="gallery/:id" element={<RequireAuth><DrawingPage /></RequireAuth>} />
                <Route path="stats" element={<RequireAuth><StatsPage /></RequireAuth>} />
                <Route path="d/:token" element={<SharedPage />} />
                <Route path="login" element={<LoginPage />} />
                <Route path="register" element={<RegisterPage />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </EngineProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
