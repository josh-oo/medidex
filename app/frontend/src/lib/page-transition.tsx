// Navigations between the pages of the app as view transitions: the header stays, the page moves a little in the
// direction of travel (a page further in comes from the right, the way back from the left) and fades across (see the
// page-transition rules in globals.css). The browser holds the old page until the new one has rendered (RootLayout
// reports it with pageCommitted), so nothing blank or half-loaded is shown in between. Links (PageLink,
// usePageNavigate) and the browser's back and forward buttons both go through it. Where the browser cannot, and with
// reduced motion, the navigation just happens.
import { forwardRef, useCallback, type ComponentProps, type MouseEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

// The longest the old page is held for a new one that is slow to render.
const MAX_WAIT_MS = 1500;

/** The page a path shows: a project's workbench is one page for all of its reports (/curation/projects/:id/...). */
export const pageKey = (pathname: string) => {
  const parts = pathname.split("/").filter(Boolean);
  return parts[0] === "curation" && parts.length > 2 ? parts.slice(0, 3).join("/") : parts.join("/");
};

// How far into the app a path is: the search (0), the database management (1), a project (2) and beyond.
const depth = (pathname: string) => {
  const parts = pathname.split("/").filter(Boolean);
  return parts[0] === "curation" ? Math.min(parts.length, 2) : parts.length === 0 ? 0 : 1;
};

/** Whether the page being shown came in with a page transition (and so needs no fade of its own). */
export const inPageTransition = () => Boolean(document.documentElement.dataset.pageTransition);

let shownPath = window.location.pathname;
let resolveCommit: (() => void) | null = null;
let running: ViewTransition | null = null;

/** Called by the layout once a page is in the DOM: a transition waiting for it may take its picture now. */
export function pageCommitted(pathname: string) {
  shownPath = pathname;
  resolveCommit?.();
  resolveCommit = null;
}

// Runs the navigation (`update`) as a page transition; false when it is not one (the same page, no support, reduced
// motion), and the caller navigates as usual.
function startPageTransition(toPath: string, update: () => void): boolean {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!document.startViewTransition || reduceMotion || pageKey(toPath) === pageKey(shownPath)) return false;

  const root = document.documentElement;
  root.dataset.pageTransition = depth(toPath) < depth(shownPath) ? "back" : "forward";
  const transition = document.startViewTransition(
    () =>
      new Promise<void>((resolve) => {
        resolveCommit = resolve;
        update();
        window.setTimeout(resolve, MAX_WAIT_MS);
      })
  );
  running = transition;
  void transition.finished.finally(() => {
    // Not when a later navigation has started a transition of its own.
    if (running === transition) delete root.dataset.pageTransition;
  });
  return true;
}

// The browser's back and forward buttons: the router hears of them only inside the transition, once the old page
// has been taken a picture of. (A capturing listener on window runs before the router's own.)
let replaying = false;
window.addEventListener(
  "popstate",
  (event) => {
    if (replaying) return;
    const started = startPageTransition(window.location.pathname, () => {
      replaying = true;
      window.dispatchEvent(new PopStateEvent("popstate", { state: event.state }));
      replaying = false;
    });
    if (started) event.stopImmediatePropagation();
  },
  { capture: true }
);

/** navigate(), as a page transition. */
export function usePageNavigate() {
  const navigate = useNavigate();

  return useCallback(
    (to: string) => {
      const toPath = new URL(to, window.location.href).pathname;
      if (!startPageTransition(toPath, () => navigate(to))) navigate(to);
    },
    [navigate]
  );
}

type PageLinkProps = Omit<ComponentProps<typeof Link>, "to"> & { to: string };

const isPlainClick = (event: MouseEvent<HTMLAnchorElement>) =>
  event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;

/** A Link whose navigation is a page transition (opening it in a new tab stays a plain link). */
export const PageLink = forwardRef<HTMLAnchorElement, PageLinkProps>(function PageLink({ to, onClick, ...props }, ref) {
  const navigate = usePageNavigate();
  return (
    <Link
      ref={ref}
      to={to}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented || !isPlainClick(event) || props.target === "_blank") return;
        event.preventDefault();
        navigate(to);
      }}
      {...props}
    />
  );
});
