import { useEffect } from "react";

// "Take me to this job's item": the queue indicator navigates to the right
// page, then calls requestFocus(targetId). Pages that hide items behind local
// UI state (VideoDetail's General/Clips tab, the clip carousel's index) react
// through useFocusTarget; the scroll + highlight itself is DOM-only, keyed on
// the `job-target-<id>` element id each item renders.

const EVENT = "h3:focus-target";
const HIGHLIGHT_CLASSES = ["ring-2", "ring-accent", "ring-offset-2", "ring-offset-bg"];
let pending: string | null = null;

export function jobTargetDomId(id: string) {
  return `job-target-${id}`;
}

export function requestFocus(targetId: string) {
  pending = targetId;
  window.dispatchEvent(new CustomEvent<string>(EVENT, { detail: targetId }));
  scrollToTarget(targetId);
}

function scrollToTarget(targetId: string) {
  const deadline = Date.now() + 5000;
  const tick = () => {
    const el = document.getElementById(jobTargetDomId(targetId));
    if (el) {
      pending = null;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add(...HIGHLIGHT_CLASSES);
      window.setTimeout(() => el.classList.remove(...HIGHLIGHT_CLASSES), 2500);
      return;
    }
    if (Date.now() < deadline) window.setTimeout(tick, 150);
  };
  tick();
}

/** Calls onFocus(id) when a focus request targets one of `ids` — on mount
 * (the request arrived while navigating here) and on later requests. */
export function useFocusTarget(ids: string[], onFocus: (id: string) => void) {
  const key = ids.join(",");
  useEffect(() => {
    const idSet = new Set(key ? key.split(",") : []);
    if (pending && idSet.has(pending)) onFocus(pending);
    const handler = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      if (idSet.has(id)) onFocus(id);
    };
    window.addEventListener(EVENT, handler);
    return () => window.removeEventListener(EVENT, handler);
    // onFocus is intentionally not a dependency: callers pass inline closures.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
