import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import TopNav from "./components/TopNav";
import QueueIndicator from "./components/QueueIndicator";
import VideosList from "./pages/VideosList";
import VideoDetail from "./pages/VideoDetail";
import CharactersList from "./pages/CharactersList";
import CharacterDetail from "./pages/CharacterDetail";
import PromptTagsList from "./pages/PromptTagsList";
import AnimateJobs from "./pages/AnimateJobs";
import SwapsList from "./pages/SwapsList";
import SwapDetail from "./pages/SwapDetail";

const rootRoute = createRootRoute({
  component: () => (
    <>
      <TopNav />
      <Outlet />
      <QueueIndicator />
    </>
  ),
});

const videosListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: VideosList,
});

const videoDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/videos/$id",
  component: VideoDetail,
});

const charactersListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/videos/$id/characters",
  component: CharactersList,
});

const characterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/videos/$id/characters/$characterId",
  component: CharacterDetail,
});

const promptTagsListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/prompt-tags",
  component: PromptTagsList,
});

const animateJobsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/animate-jobs",
  component: AnimateJobs,
});

const swapsListRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/swaps",
  component: SwapsList,
});

const swapDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/swaps/$id",
  component: SwapDetail,
});

const routeTree = rootRoute.addChildren([
  videosListRoute,
  videoDetailRoute,
  charactersListRoute,
  characterDetailRoute,
  promptTagsListRoute,
  animateJobsRoute,
  swapsListRoute,
  swapDetailRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
