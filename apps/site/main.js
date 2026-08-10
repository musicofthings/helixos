const themeToggle = document.querySelector("[data-theme-toggle]");
const themeRoot = document.documentElement;

const applyTheme = (theme) => {
  const nextTheme = theme === "dark" ? "dark" : "light";
  if (nextTheme === "dark") {
    themeRoot.dataset.theme = "dark";
  } else {
    delete themeRoot.dataset.theme;
  }

  if (themeToggle) {
    const isDark = nextTheme === "dark";
    themeToggle.textContent = isDark ? "Dark theme" : "Light pastel";
    themeToggle.setAttribute("aria-label", isDark ? "Switch to light pastel theme" : "Switch to dark theme");
    themeToggle.setAttribute("aria-pressed", String(isDark));
  }
};

try {
  const savedTheme = localStorage.getItem("helixos-theme");
  applyTheme(savedTheme === "dark" ? "dark" : "light");
} catch (error) {
  applyTheme("light");
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const nextTheme = themeRoot.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    try {
      localStorage.setItem("helixos-theme", nextTheme);
    } catch (error) {
      // Theme preference is optional; fall back to the current session only.
    }
  });
}

const revealTargets = document.querySelectorAll(".band, .split, .start-grid, .foot");

for (const el of revealTargets) {
  el.classList.add("reveal");
}

const observer = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        observer.unobserve(entry.target);
      }
    }
  },
  { threshold: 0.16 }
);

for (const el of revealTargets) {
  observer.observe(el);
}

// Subtle parallax on the hero stage for presence without noise.
const stage = document.querySelector(".hero-stage");
if (stage && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  window.addEventListener(
    "pointermove",
    (event) => {
      const x = (event.clientX / window.innerWidth - 0.5) * 8;
      const y = (event.clientY / window.innerHeight - 0.5) * 6;
      stage.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    },
    { passive: true }
  );
}

const modelShell = document.querySelector("[data-model-shell]");
const modelElement = document.querySelector("#lab-model");

if (modelShell && modelElement) {
  // If the GLB fails to load, hide the shell so the poster image shows cleanly.
  modelElement.addEventListener("error", () => {
    modelShell.style.minHeight = "auto";
  });
}
