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

const reasonSelect = document.querySelector("[data-contact-reason-select]");
const reasonTriggers = document.querySelectorAll("[data-contact-reason]");

for (const trigger of reasonTriggers) {
  trigger.addEventListener("click", () => {
    if (reasonSelect) {
      reasonSelect.value = trigger.dataset.contactReason;
    }
  });
}

const contactForm = document.querySelector("[data-contact-form]");
const formStatus = document.querySelector("[data-form-status]");

if (contactForm && formStatus) {
  contactForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const submitButton = contactForm.querySelector("button[type='submit']");
    const formData = new FormData(contactForm);

    submitButton.disabled = true;
    formStatus.textContent = "Sending…";
    formStatus.dataset.state = "pending";

    try {
      const response = await fetch(contactForm.action, {
        method: "POST",
        body: formData,
        headers: { Accept: "application/json" },
      });

      if (response.ok) {
        formStatus.textContent = "Thanks — we'll be in touch shortly.";
        formStatus.dataset.state = "success";
        contactForm.reset();
      } else {
        throw new Error("Form submission failed");
      }
    } catch (error) {
      formStatus.innerHTML =
        'Something went wrong. Please <a href="https://github.com/musicofthings/helixos/discussions/new?category=general">reach out via GitHub Discussions</a> instead.';
      formStatus.dataset.state = "error";
    } finally {
      submitButton.disabled = false;
    }
  });
}
