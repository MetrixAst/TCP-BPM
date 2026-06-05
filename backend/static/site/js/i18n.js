(function (window) {
  'use strict';

  var SKIP_TAGS = {
    SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, CODE: 1, PRE: 1, TEXTAREA: 1,
  };

  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];

  window.BPM_I18N = window.BPM_I18N || { lang: 'ru' };
  window.BPM = window.BPM || {};

  function currentLang() {
    return (window.BPM_I18N && window.BPM_I18N.lang) || document.documentElement.lang || 'ru';
  }

  function normalize(text) {
    return text.replace(/\s+/g, ' ').trim();
  }

  function getMap(lang) {
    var bundle = window.BPM_TRANSLATIONS;
    if (!bundle) return null;
    if (lang === 'kk') return bundle.kk;
    if (lang === 'en') return bundle.en;
    return null;
  }

  function getByPath(obj, path) {
    if (!obj || !path) return undefined;
    return path.split('.').reduce(function (acc, key) {
      return acc && acc[key] !== undefined ? acc[key] : undefined;
    }, obj);
  }
  
  function translateDataI18n(root, map) {
    if (!root || !map) return;
  
    root.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      var val = getByPath(map, key);
      if (val !== undefined) el.textContent = val;
    });
  
    ['placeholder', 'title', 'aria-label', 'alt'].forEach(function (attr) {
      root.querySelectorAll('[data-i18n-' + attr + ']').forEach(function (el) {
        var key = el.getAttribute('data-i18n-' + attr);
        var val = getByPath(map, key);
        if (val !== undefined) el.setAttribute(attr, val);
      });
    });
  }
  // Только полное совпадение — никаких подстрок
  function translateText(text, map) {
    var norm = normalize(text);
    if (!norm || !map) return text;
    if (map[norm] !== undefined) {
      var lead  = text.match(/^\s*/)[0];
      var trail = text.match(/\s*$/)[0];
      return lead + map[norm] + trail;
    }
    return text;
  }

  function shouldSkipNode(node) {
    var p = node.parentElement;
    while (p) {
      if (p.classList && p.classList.contains('bpm-no-translate')) return true;
      if (SKIP_TAGS[p.tagName]) return true;
      p = p.parentElement;
    }
    return false;
  }

  function translateAttributes(el, map) {
    ATTRS.forEach(function (attr) {
      if (!el.hasAttribute(attr)) return;
      var val  = el.getAttribute(attr);
      var next = translateText(val, map);
      if (next !== val) el.setAttribute(attr, next);
    });
  }

  function walkRoot(root, map) {
    if (!root) return;
    translateDataI18n(root, map);

    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node.nodeValue || !normalize(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        if (shouldSkipNode(node)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    var node;
    while ((node = walker.nextNode())) {
      var next = translateText(node.nodeValue, map);
      if (next !== node.nodeValue) node.nodeValue = next;
    }

    root.querySelectorAll('*').forEach(function (el) {
      if (el.hasAttribute('data-i18n-skip')) return;
      if (el.classList.contains('bpm-no-translate')) return;
    
      translateAttributes(el, map);
    
      if (el.tagName === 'OPTION') {
        var current = normalize(el.textContent);
        if (map[current]) {
          el.textContent = map[current];
        }
      }
    });
  }


  function refreshSelect2Placeholders(map) {
    if (!map) return;
    if (typeof window.jQuery === 'undefined' || !window.jQuery.fn.select2) return;

    var $ = window.jQuery;

    $('select.select2-hidden-accessible').each(function () {
      var $sel = $(this);

      // Берём текущий placeholder из rendered .select2-selection__placeholder
      var $ph = $sel.next('.select2-container').find('.select2-selection__placeholder');
      if (!$ph.length) return;

      var current = normalize($ph.text());
      if (!current || !map[current]) return;

      // Обновляем placeholder через Select2 settings
      var settings = $sel.data('select2');
      if (settings && settings.options && settings.options.options) {
        var opts = settings.options.options;
        if (opts.placeholder && typeof opts.placeholder === 'string') {
          opts.placeholder = map[normalize(opts.placeholder)] || opts.placeholder;
        }
      }

      // Перерисовываем selection (самый надёжный способ)
      $ph.text(map[current]);
    });
  }

  window.BPM.applyTranslations = function (lang) {
    lang = lang || currentLang();

    if (lang === 'ru') {
      document.documentElement.classList.add('i18n-ready');
      document.documentElement.removeAttribute('data-i18n-pending');
      return;
    }

    var map = getMap(lang);
    if (!map) {
      document.documentElement.classList.add('i18n-ready');
      return;
    }

    // Переводим все зоны
    walkRoot(document.getElementById('bpmSidebar'), map);
    walkRoot(document.getElementById('bpmMain'),    map);
    walkRoot(document.querySelector('.bpm-topbar'), map);
    walkRoot(document.querySelector('.auth-page'),  map);
    walkRoot(document.body, map);

    if (document.title) {
      document.title = translateText(document.title, map);
    }

    document.documentElement.lang = lang;
    document.documentElement.classList.add('i18n-ready');
    document.documentElement.removeAttribute('data-i18n-pending');

    // Select2 инициализируется после DOMContentLoaded в tasks.js.
    // Запускаем обновление плейсхолдеров с небольшой задержкой,
    // чтобы Select2 точно успел отрисоваться.
    setTimeout(function () {
      refreshSelect2Placeholders(map);
    }, 150);
  };

  window.BPM.t = function (key, fallback) {
    if (window.BPM_I18N[key]) return window.BPM_I18N[key];
    var lang = currentLang();
    if (lang === 'ru') return fallback !== undefined ? fallback : key;
    var map = getMap(lang);
    if (map && fallback && map[normalize(fallback)]) return map[normalize(fallback)];
    return fallback !== undefined ? fallback : key;
  };

  function boot() {
    var lang = currentLang();
    if (lang !== 'ru') document.documentElement.setAttribute('data-i18n-pending', '1');
    window.BPM.applyTranslations(lang);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);