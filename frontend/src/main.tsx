import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { LocaleProvider } from "./i18n/LocaleContext";
import { retryDelay, shouldRetry } from "./query/policy";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: shouldRetry,
      retryDelay,
      refetchOnWindowFocus: true,
      refetchIntervalInBackground: false,
    },
    mutations: { retry: false },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("Root element is missing");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <LocaleProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </LocaleProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
