import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { LocaleProvider } from "./i18n/LocaleContext";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./styles/fonts.css";
import "./styles.css";
import "./styles/tokens.css";
import "./styles/reset.css";
import "./styles/primitives.css";
import "./styles/shell.css";
import "./styles/patterns.css";
import "./styles/visualizations.css";
import "./styles/pages/login.css";
import "./styles/pages/overview.css";
import "./styles/pages/overview-layout.css";
import "./styles/pages/alerts.css";
import "./styles/pages/incidents.css";
import "./styles/pages/endpoints-events.css";
import "./styles/pages/intelligence-operations.css";
import "./styles/pages/details.css";
import "./styles/report.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      retryOnMount: false,
      refetchOnMount: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchIntervalInBackground: false,
      networkMode: "always",
    },
    mutations: { retry: false },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("Root element is missing");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <LocaleProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </LocaleProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
