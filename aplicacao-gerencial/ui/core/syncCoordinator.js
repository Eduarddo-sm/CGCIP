const DEFAULT_TICK_MS = 15000;

export function startSyncCoordinator(options = {}) {
  const {
    getMode = () => "",
    refreshOverview = async () => {},
    refreshMainHub = async () => {},
    refreshNotifications = async () => {},
    tickMs = DEFAULT_TICK_MS,
  } = options;

  let timer = null;
  let bootstrapTimer = null;
  let running = false;
  let tickCount = 0;
  let lastRunAt = 0;

  async function run({ force = false } = {}) {
    if (running || (!force && document.hidden)) return;
    running = true;
    lastRunAt = Date.now();
    tickCount += 1;
    try {
      const mode = getMode();
      const jobs = [];

      if (mode === "mainhub") jobs.push(refreshMainHub());
      else if (mode === "overview") jobs.push(refreshOverview());

      if (tickCount % 2 === 0) jobs.push(refreshNotifications());
      if (jobs.length) await Promise.allSettled(jobs);
    } finally {
      running = false;
    }
  }

  function handleVisibilityChange() {
    if (!document.hidden && Date.now() - lastRunAt >= tickMs) run({ force: true });
  }

  window.clearInterval(timer);
  timer = window.setInterval(run, tickMs);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  bootstrapTimer = window.setTimeout(() => refreshNotifications(), 1200);

  return () => {
    window.clearInterval(timer);
    window.clearTimeout(bootstrapTimer);
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  };
}
