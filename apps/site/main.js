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
