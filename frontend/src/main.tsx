import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { RouterProvider } from "@tanstack/react-router";
import { Toaster } from "sonner";
import "@vidstack/react/player/styles/base.css";
import "@vidstack/react/player/styles/default/theme.css";
import "@vidstack/react/player/styles/default/icons.css";
import "@vidstack/react/player/styles/default/buttons.css";
import "@vidstack/react/player/styles/default/controls.css";
import "@vidstack/react/player/styles/default/sliders.css";
import "@vidstack/react/player/styles/default/time.css";
import "@vidstack/react/player/styles/default/tooltips.css";
import "@vidstack/react/player/styles/default/menus.css";
import "@vidstack/react/player/styles/default/captions.css";
import "@vidstack/react/player/styles/default/chapter-title.css";
import "@vidstack/react/player/styles/default/poster.css";
import "@vidstack/react/player/styles/default/buffering.css";
import "@vidstack/react/player/styles/default/gestures.css";
import "@vidstack/react/player/styles/default/keyboard.css";
import "@vidstack/react/player/styles/default/layouts/video.css";
import "./index.css";
import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("root element not found");

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      {/* Offset so toasts stack above the queue widget (components/QueueIndicator) in the same corner. */}
      <Toaster richColors position="bottom-right" theme="dark" offset={{ bottom: 72, right: 16 }} />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </StrictMode>,
);
