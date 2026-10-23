/* Песни на стихи П.Л. Драверта: the only custom JavaScript on the site.
   1. Theme toggle (light / dark, remembered in localStorage, follows the system by default)
   2. Audio player (play/pause, seek, elapsed/total time, equalizer state, "player started" signal)
   Offcanvas (mobile song list) is handled by bootstrap.bundle.min.js via data-bs-* attributes. */

/* ---------- 1. Theme ---------- */
(function () {
  var root = document.documentElement;

  function storedTheme() {
    try { return localStorage.getItem('theme'); } catch (e) { return null; }
  }

  document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var next = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-bs-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
    });
  });

  // Until the visitor makes an explicit choice, follow the operating system.
  if (window.matchMedia) {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (!storedTheme()) root.setAttribute('data-bs-theme', e.matches ? 'dark' : 'light');
    });
  }
})();

/* ---------- 2. Audio player ---------- */
(function () {
  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    return Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
  }

  function initPlayer(el) {
    var btn = el.querySelector('[data-play]');
    var range = el.querySelector('input[type=range]');
    var seek = el.querySelector('[data-seek]');
    var time = el.querySelector('[data-time]');
    var eq = el.querySelector('[data-eq]');
    var icons = {
      play: el.querySelector('[data-icon=play]'),
      pause: el.querySelector('[data-icon=pause]'),
      loading: el.querySelector('[data-icon=loading]')
    };
    var total = parseFloat(el.dataset.duration) || 0;
    var reported = false;                      // "player started" is sent once per page view

    var audio = new Audio();
    audio.preload = 'none';                    // do not download the MP3 until Play is pressed
    audio.src = el.dataset.src;

    function setState(state) {                 // idle | loading | playing | paused
      el.dataset.state = state;
      eq.classList.toggle('is-playing', state === 'playing');
      // toggleAttribute (not the .hidden property): the icons are SVG elements. Bootstrap styles [hidden] as display:none.
      icons.play.toggleAttribute('hidden', !(state === 'idle' || state === 'paused'));
      icons.pause.toggleAttribute('hidden', state !== 'playing');
      icons.loading.toggleAttribute('hidden', state !== 'loading');
      range.disabled = state === 'loading';
      btn.setAttribute('aria-label', state === 'playing' ? 'Пауза' : state === 'loading' ? 'Загрузка' : 'Воспроизвести');
    }

    function render() {
      var dur = isFinite(audio.duration) && audio.duration > 0 ? audio.duration : total;
      var cur = audio.currentTime || 0;
      range.max = Math.floor(dur) || 0;
      range.value = Math.floor(cur);
      seek.style.setProperty('--dr-pos', (dur ? (cur / dur) * 100 : 0).toFixed(1) + '%');
      time.textContent = fmt(cur) + ' / ' + fmt(dur);
    }

    function signalStarted() {
      if (reported || !el.dataset.startUrl) return;
      reported = true;
      // Fire-and-forget. The server decides whether this counts (once per IP + song cookie, 1 hour).
      fetch(el.dataset.startUrl, { method: 'POST', credentials: 'same-origin', keepalive: true }).catch(function () {});
    }

    btn.addEventListener('click', function () {
      if (audio.paused) {
        setState('loading');
        audio.play().catch(function () { setState('idle'); });
      } else {
        audio.pause();
      }
    });

    range.addEventListener('input', function () {
      audio.currentTime = Number(range.value);
      render();
    });

    audio.addEventListener('waiting', function () { setState('loading'); });
    audio.addEventListener('playing', function () { setState('playing'); signalStarted(); });
    audio.addEventListener('pause', function () { if (!audio.ended) setState('paused'); });
    audio.addEventListener('ended', function () { audio.currentTime = 0; setState('idle'); render(); });
    audio.addEventListener('error', function () { setState('idle'); });
    audio.addEventListener('loadedmetadata', render);
    audio.addEventListener('timeupdate', render);

    setState('idle');
    render();
  }

  document.querySelectorAll('.dr-player').forEach(initPlayer);
})();
