/* Admin-only JavaScript, loaded only for the logged-in administrator.
   1. Pencil buttons ([data-edit-text]) open the shared text editor modal from base.html.
   2. Forms with data-confirm ask before submitting (deletions). */

(function () {
  var modalEl = document.getElementById('text-modal');
  if (modalEl) {
    var form = modalEl.querySelector('form');
    var textarea = form.elements.value;
    var rows = { line: 2, text: 5, html: 16 };

    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-edit-text]');
      if (!btn) return;
      e.preventDefault();
      var kind = btn.dataset.kind || 'line';
      form.elements.key.value = btn.dataset.editText;
      form.elements.restore_default.checked = false;
      textarea.value = btn.dataset.value || '';
      textarea.rows = rows[kind] || 3;
      textarea.dataset.kind = kind;
      textarea.classList.toggle('font-monospace', kind === 'html');
      modalEl.querySelector('[data-label]').textContent = btn.dataset.label || 'Текст';
      modalEl.querySelector('[data-hint]').textContent = btn.dataset.hint || '';
      modalEl.querySelector('[data-html-hint]').hidden = kind !== 'html';
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    });

    modalEl.addEventListener('shown.bs.modal', function () { textarea.focus(); });

    // Single-line texts: Enter saves instead of adding a line break.
    textarea.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && textarea.dataset.kind === 'line') {
        e.preventDefault();
        form.requestSubmit();
      }
    });
  }

  document.addEventListener('submit', function (e) {
    var message = e.target.dataset.confirm;
    if (message && !window.confirm(message)) e.preventDefault();
  });
})();
