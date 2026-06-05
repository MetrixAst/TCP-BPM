/**
 * BPM language switcher (native i18n via ?lang= + i18n-bundle.js).
 * Links in templates use {% lang_url %}; this helper is for programmatic switches.
 */
(function () {
  'use strict';

  window.bpmSetLang = function (lang) {
    var url = new URL(window.location.href);
    url.searchParams.set('lang', lang);
    window.location.href = url.toString();
  };
})();
