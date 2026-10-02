import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { LoginPage, RegisterPage } from "./features/auth/AuthPages";
import { LandingPage } from "./features/landing/LandingPage";
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
