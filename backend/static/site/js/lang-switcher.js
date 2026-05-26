/**
 * BPM Language Switcher via Google Translate
 * Шаблоны остаются на русском. Google переводит весь контент.
 */
(function () {
  'use strict';

  var COOKIE_BPM  = 'bpm_lang';
  var COOKIE_GT   = 'googtrans';
  var ONE_YEAR    = 60 * 60 * 24 * 365;

  function setCookie(name, value, maxAge) {
    var base = name + '=' + encodeURIComponent(value) + '; path=/; samesite=lax';
    if (maxAge) base += '; max-age=' + maxAge;
    document.cookie = base;
    // Google Translate иногда читает домен с точкой
    document.cookie = base + '; domain=.' + location.hostname;
  }

  function deleteCookie(name) {
    var expired = '; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/';
    document.cookie = name + '=' + expired;
    document.cookie = name + '=' + expired + '; domain=.' + location.hostname;
  }

  window.bpmSetLang = function (lang) {
    // 1. Сохраняем выбор пользователя (для подсветки активной кнопки)
    setCookie(COOKIE_BPM, lang, ONE_YEAR);

    // 2. Управляем Google Translate
    if (lang === 'ru') {
      deleteCookie(COOKIE_GT);
    } else {
      // /auto/kk или /ru/en — Google Translate формат
      setCookie(COOKIE_GT, '/ru/' + lang);
    }

    // 3. Перезагружаем страницу
    location.reload();
  };

  // Инициализация виджета Google Translate (скрытый)
  window.googleTranslateElementInit = function () {
    new google.translate.TranslateElement({
      pageLanguage: 'ru',
      includedLanguages: 'kk,en,ru',
      autoDisplay: false
    }, 'bpm-gt-root');
  };
})();
