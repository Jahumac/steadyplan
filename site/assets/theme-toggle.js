(function () {
  const STORAGE_KEY = 'steadyplan-site-theme';
  const root = document.documentElement;

  function applyTheme(theme) {
    const nextTheme = theme === 'dark' ? 'dark' : 'light';
    root.dataset.theme = nextTheme;
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const darkEnabled = nextTheme === 'dark';
      button.setAttribute('aria-pressed', darkEnabled ? 'true' : 'false');
      button.setAttribute('aria-label', darkEnabled ? 'Switch to light mode' : 'Switch to dark mode');
      button.textContent = darkEnabled ? 'Light mode' : 'Dark mode';
    });
  }

  function readStoredTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function storeTheme(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (error) {
      // Ignore storage failures; the toggle should still work for this page view.
    }
  }

  applyTheme(readStoredTheme() || root.dataset.theme || 'light');

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.addEventListener('click', function () {
        const nextTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
        applyTheme(nextTheme);
        storeTheme(nextTheme);
      });
    });
  });
})();
