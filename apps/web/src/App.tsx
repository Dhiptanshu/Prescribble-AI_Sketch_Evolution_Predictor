import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { ChallengePage } from "./features/challenge/ChallengePage";
import { AdminPage } from "./features/admin/AdminPage";
import { LoginPage, RegisterPage } from "./features/auth/AuthPages";
import { DevelopersPage } from "./features/developers/DevelopersPage";
import { DrawingPage } from "./features/gallery/DrawingPage";
import { GalleryPage } from "./features/gallery/GalleryPage";
import { LandingPage } from "./features/landing/LandingPage";
import { SettingsPage } from "./features/settings/SettingsPage";
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
                <Route path="challenge" element={<ChallengePage />} />
                <Route path="developers" element={<DevelopersPage />} />
                <Route path="admin" element={<AdminPage />} />
                <Route path="settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
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
