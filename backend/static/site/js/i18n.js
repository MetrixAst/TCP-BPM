/**
 * Клиентский переводчик BPM: шаблоны остаются на русском,
 * при lang=kk|en подставляет текст из window.BPM_TRANSLATIONS.
 *
 * FIX [UAT-01]: убран substring replace — теперь только exact match.
 * Пользовательский контент: названия задач, ФИО, комментарии — не затрагивается.
 * Элементы с классом bpm-no-translate и их потомки пропускаются.
 */
(function (window) {
  'use strict';

  var SKIP_TAGS = {
    SCRIPT: 1,
    STYLE: 1,
    NOSCRIPT: 1,
    CODE: 1,
    PRE: 1,
    TEXTAREA: 1,
  };

  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];

  window.BPM_I18N = window.BPM_I18N || { lang: 'ru' };
  window.BPM = window.BPM || {};

  function currentLang() {
    return (window.BPM_I18N && window.BPM_I18N.lang) || document.documentElement.lang || 'ru';
  }

  function normalize(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  }

  function getMap(lang) {
    var bundle = window.BPM_TRANSLATIONS;
    if (!bundle) return null;
    if (lang === 'kk') return bundle.kk;
    if (lang === 'en') return bundle.en;
    return null;
  }

  function translateText(text, map) {
    if (!map) return text;

    var norm = normalize(text);
    if (!norm) return text;

    if (Object.prototype.hasOwnProperty.call(map, norm)) {
      var lead = String(text).match(/^\s*/)[0];
      var trail = String(text).match(/\s*$/)[0];
      return lead + map[norm] + trail;
    }

    return text;
  }

  function shouldSkipNode(node) {
    var p = node.parentElement;

    while (p) {
      if (p.hasAttribute && p.hasAttribute('data-i18n-skip')) return true;
      if (p.classList && p.classList.contains('bpm-no-translate')) return true;
      if (SKIP_TAGS[p.tagName]) return true;
      p = p.parentElement;
    }

    return false;
  }

  function shouldSkipElement(el) {
    if (!el) return true;
    if (el.hasAttribute && el.hasAttribute('data-i18n-skip')) return true;
    if (el.classList && el.classList.contains('bpm-no-translate')) return true;
    if (SKIP_TAGS[el.tagName]) return true;
    return false;
  }

  function translateAttributes(el, map) {
    ATTRS.forEach(function (attr) {
      if (!el.hasAttribute(attr)) return;

      var val = el.getAttribute(attr);
      var next = translateText(val, map);

      if (next !== val) {
        el.setAttribute(attr, next);
      }
    });
  }

  function walkRoot(root, map) {
    if (!root || !map) return;

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
      if (next !== node.nodeValue) {
        node.nodeValue = next;
      }
    }

    root.querySelectorAll('*').forEach(function (el) {
      if (shouldSkipElement(el)) return;

      translateAttributes(el, map);

      if (el.tagName === 'OPTION') {
        var next = translateText(el.textContent, map);
        if (next !== el.textContent) {
          el.textContent = next;
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
      var $ph = $sel.next('.select2-container').find('.select2-selection__placeholder');

      if (!$ph.length) return;

      var current = normalize($ph.text());
      if (!current || !map[current]) return;

      var settings = $sel.data('select2');
      if (settings && settings.options && settings.options.options) {
        var opts = settings.options.options;

        if (opts.placeholder && typeof opts.placeholder === 'string') {
          opts.placeholder = map[normalize(opts.placeholder)] || opts.placeholder;
        }
      }

      $ph.text(map[current]);
    });
  }

  window.BPM._walkTextNodes = walkTextNodes;
  window.BPM.applyTranslations = function (lang) {
    lang = lang || currentLang();

    if (lang === 'ru') {
      document.documentElement.lang = 'ru';
      document.documentElement.classList.add('i18n-ready');
      document.documentElement.removeAttribute('data-i18n-pending');
      return;
    }

    var map = getMap(lang);

    if (!map) {
      document.documentElement.classList.add('i18n-ready');
      document.documentElement.removeAttribute('data-i18n-pending');
      return;
    }

    var root = document.body;
    walkTextNodes(root, map, bundle.keysSorted);

    if (document.title) {
      document.title = translateText(document.title, map);
    }

    document.documentElement.lang = lang;
    document.documentElement.classList.add('i18n-ready');
    document.documentElement.removeAttribute('data-i18n-pending');

    setTimeout(function () {
      refreshSelect2Placeholders(map);
    }, 150);
  };

  window.BPM.t = function (key, fallback) {
    if (window.BPM_I18N[key]) return window.BPM_I18N[key];

    var lang = currentLang();
    if (lang === 'ru') return fallback !== undefined ? fallback : key;

    var map = getMap(lang);
    if (map && fallback && map[normalize(fallback)]) {
      return map[normalize(fallback)];
    }

    return fallback !== undefined ? fallback : key;
  };

  function saveOriginals() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        if (!node.nodeValue || !normalize(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        if (shouldSkipNode(node)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var node;
    while ((node = walker.nextNode())) {
      if (!node._bpmOriginal) {
        node._bpmOriginal = node.nodeValue;
      }
    }
    document.querySelectorAll('*').forEach(function(el) {
      ATTRS.forEach(function(attr) {
        if (!el.hasAttribute(attr)) return;
        var origAttr = 'data-orig-' + attr;
        if (!el.hasAttribute(origAttr)) {
          el.setAttribute(origAttr, el.getAttribute(attr));
        }
      });
    });
  }

  function boot() {
    var lang = currentLang();

    if (lang !== 'ru') {
      document.documentElement.setAttribute('data-i18n-pending', '1');
    }
    saveOriginals();
    window.BPM.applyTranslations(lang);
    if (lang !== 'ru') {
      setTimeout(function() {
        saveOriginals();
        window.BPM.applyTranslations(lang);
      }, 300);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.BPM.switchLang = function (lang) {
    document.cookie = 'bpm_lang=' + lang + ';path=/;max-age=' + (60*60*24*365) + ';samesite=Lax';
    var url = new URL(window.location.href);
    url.searchParams.delete('lang');
    window.location.href = url.toString();
  };
})(window);
