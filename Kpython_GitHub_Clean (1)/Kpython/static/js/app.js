document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const menuToggle = document.getElementById('menu-toggle');

  menuToggle?.addEventListener('click', () => {
    const open = sidebar?.classList.toggle('is-open');
    menuToggle.setAttribute('aria-expanded', String(Boolean(open)));
  });

  document.addEventListener('click', (event) => {
    if (window.innerWidth <= 760 && sidebar?.classList.contains('is-open') &&
        !sidebar.contains(event.target) && !menuToggle?.contains(event.target)) {
      sidebar.classList.remove('is-open');
      menuToggle?.setAttribute('aria-expanded', 'false');
    }
  });

  document.querySelectorAll('.flash-close').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const quantityInputs = [...document.querySelectorAll('input[name^="quantity_"]')];
  const totalElement = document.getElementById('order-total');
  const countElement = document.getElementById('item-count');
  const updateOrderSummary = () => {
    let total = 0;
    let count = 0;
    quantityInputs.forEach((input) => {
      const quantity = Math.max(0, Number.parseInt(input.value || '0', 10) || 0);
      total += quantity * Number(input.dataset.price || 0);
      count += quantity;
    });
    if (totalElement) totalElement.textContent = `NGN ${new Intl.NumberFormat('en-NG', { maximumFractionDigits: 0 }).format(total)}`;
    if (countElement) countElement.textContent = String(count);
  };
  quantityInputs.forEach((input) => input.addEventListener('input', updateOrderSummary));
  updateOrderSummary();
});
