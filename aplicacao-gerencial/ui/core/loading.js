export function skeletonList(count = 5) {
  return `
    <div class="skeleton-list" aria-hidden="true">
      ${Array.from({ length: count }).map(() => `
        <div class="skeleton-card">
          <span class="skeleton-pill"></span>
          <span class="skeleton-line wide"></span>
          <span class="skeleton-line"></span>
        </div>
      `).join("")}
    </div>
  `;
}

export function skeletonStats(count = 3) {
  return Array.from({ length: count }).map(() => `
    <article class="stats-card skeleton-card" aria-hidden="true">
      <span class="skeleton-line"></span>
      <span class="skeleton-number"></span>
    </article>
  `).join("");
}

export function setLoading(target, markup = skeletonList()) {
  const element = typeof target === "string" ? document.querySelector(target) : target;
  if (!element) return;
  element.classList.add("is-loading");
  element.innerHTML = markup;
}

export function clearLoading(target) {
  const element = typeof target === "string" ? document.querySelector(target) : target;
  if (!element) return;
  element.classList.remove("is-loading");
}
