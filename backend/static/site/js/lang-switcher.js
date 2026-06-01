/**
 * BPM Language Switcher (FE-FIX-03).
 * Только JSON-движок, без Google Translate.
 *
 * Логика:
 *  1. Читает cookie bpm_lang (ru/kk/en)
 *  2. Подсвечивает активную кнопку
 *  3. По клику пишет cookie, удаляет старый googtrans (на случай если остался),
 *     перезагружает страницу
 *  4. i18n.js читает window.BPM_I18N.lang и переводит DOM из BPM_TRANSLATIONS
 *  5. Фразы которых нет в словаре — остаются на русском
 */
(function (window, document) {
  'use strict';

  var COOKIE = 'bpm_lang';
  var LANGS = ['ru', 'kk', 'en'];
  var ONE_YEAR = 60 * 60 * 24 * 365;

  function setCookie(name, value) {
    document.cookie = name + '=' + encodeURIComponent(value) +
      '; path=/; max-age=' + ONE_YEAR + '; samesite=lax';
  }

  function getCookie(name) {
    var m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
    return m ? decodeURIComponent(m[1]) : null;
  }

  function deleteCookie(name) {
    var expired = '; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/';
    document.cookie = name + '=' + expired;
    document.cookie = name + '=' + expired + '; domain=.' + location.hostname;
  }

  function currentLang() {
    var lang = getCookie(COOKIE) ||
               (window.BPM_I18N && window.BPM_I18N.lang) ||
               document.documentElement.lang ||
               'ru';
    return LANGS.indexOf(lang) !== -1 ? lang : 'ru';
  }

  function highlightActive(lang) {
    document.querySelectorAll('.bpm-topbar__lang-btn').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.dataset.lang === lang);
    });
  }

  function boot() {
    // На случай если раньше был Google Translate — чистим его cookie
    deleteCookie('googtrans');

    var lang = currentLang();

    if (window.BPM_I18N) {
      window.BPM_I18N.lang = lang;
    }

    highlightActive(lang);

    document.querySelectorAll('.bpm-topbar__lang-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var newLang = btn.dataset.lang;
        if (LANGS.indexOf(newLang) === -1) return;
        setCookie(COOKIE, newLang);
        location.reload();
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window, document);