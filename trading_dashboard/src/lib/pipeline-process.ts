// Cross-route singleton holding the currently-running pipeline child
// process. Lives in `lib/` (not in any one route file) so both the
// run route (which spawns) and the stop route (which kills) import
// from the same module — Next.js shares the module between them.
//
// Module-level mutable state in a stateless framework is unusual, but
// the dashboard is local-only / single-user / single-pipeline-at-a-
// time, so a singleton is the simplest correct model. In dev with hot
// reload, restarting the module loses the reference and the child
// becomes a zombie until the user `pkill`s it. Acceptable for this
// scope.

import type { ChildProcessWithoutNullStreams } from "child_process";

let activeChild: ChildProcessWithoutNullStreams | null = null;

export function setActiveChild(c: ChildProcessWithoutNullStreams | null): void {
  activeChild = c;
}

export function hasActiveChild(): boolean {
  return activeChild !== null;
}

// Send a signal (default SIGTERM) to the active child, if any. Returns
// true if a child existed and the signal was queued, false if no child
// was running. The exit handler set up at spawn time will clear the
// reference once the process actually dies.
export function killActiveChild(signal: NodeJS.Signals = "SIGTERM"): boolean {
  if (!activeChild) return false;
  try {
    activeChild.kill(signal);
    return true;
  } catch {
    return false;
  }
}
