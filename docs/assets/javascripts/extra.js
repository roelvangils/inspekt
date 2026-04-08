/**
 * Zen Browser Bridge - Custom JavaScript
 * Enhanced documentation interactivity
 */

document.addEventListener('DOMContentLoaded', function() {

  // Add smooth scrolling to anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (href !== '#') {
        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
          target.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      }
    });
  });

  // Add copy button feedback
  const copyButtons = document.querySelectorAll('.md-clipboard');
  copyButtons.forEach(button => {
    button.addEventListener('click', function() {
      const icon = this.querySelector('svg');
      if (icon) {
        // Temporary visual feedback
        icon.style.transform = 'scale(1.2)';
        setTimeout(() => {
          icon.style.transform = 'scale(1)';
        }, 200);
      }
    });
  });

  // Enhance external links
  document.querySelectorAll('a[href^="http"]').forEach(link => {
    // Skip if it's an internal link to the docs
    if (!link.href.includes('roelvangils.github.io/inspekt-bridge')) {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    }
  });

  // Add table responsiveness
  document.querySelectorAll('table').forEach(table => {
    if (!table.parentElement.classList.contains('table-wrapper')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-wrapper';
      wrapper.style.overflowX = 'auto';
      wrapper.style.margin = '1.5em 0';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  });

  // Enhance Mermaid diagrams with loading states
  const mermaidDiagrams = document.querySelectorAll('.mermaid');
  mermaidDiagrams.forEach(diagram => {
    // Add a subtle fade-in effect once loaded
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.target.querySelector('svg')) {
          mutation.target.style.opacity = '0';
          mutation.target.style.transition = 'opacity 0.3s ease';
          setTimeout(() => {
            mutation.target.style.opacity = '1';
          }, 100);
          observer.disconnect();
        }
      });
    });
    observer.observe(diagram, { childList: true, subtree: true });
  });

  // Add keyboard shortcuts info (optional)
  document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + K for search focus
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const searchInput = document.querySelector('.md-search__input');
      if (searchInput) {
        searchInput.focus();
      }
    }
  });

  // Add "Back to Top" functionality enhancement
  const backToTop = document.querySelector('[href="#"]');
  if (backToTop) {
    backToTop.addEventListener('click', function(e) {
      e.preventDefault();
      window.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
    });
  }

  console.log('Zen Bridge docs enhanced! ⚡');
});
