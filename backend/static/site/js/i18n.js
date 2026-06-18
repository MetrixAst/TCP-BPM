/**
 * Клиентский переводчик BPM: шаблоны остаются на русском,
 * при lang=kk|en подставляет текст из window.BPM_TRANSLATIONS (i18n-bundle.js).
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

  var ATTRS = ['placeholder', 'title', 'aria-label', 'alt', 'data-placeholder'];

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

  function translateText(text, map, keysSorted) {
    var norm = normalize(text);
    if (!norm || !map) return text;

    if (map[norm] !== undefined) {
      return preserveEdges(text, norm, map[norm]);
    }

    if (keysSorted) {
      for (var i = 0; i < keysSorted.length; i++) {
        var key = keysSorted[i];
        if (key.length < 2) continue;
        if (norm.indexOf(key) !== -1 && map[key]) {
          return text.split(key).join(map[key]);
        }
      }
    }
    return text;
  }

  function preserveEdges(original, norm, translated) {
    var lead = original.match(/^\s*/)[0];
    var trail = original.match(/\s*$/)[0];
    return lead + translated + trail;
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

  function translateAttributes(el, map, keysSorted) {
    ATTRS.forEach(function (attr) {
      if (!el.hasAttribute(attr)) return;
      var val = el.getAttribute(attr);
      var next = translateText(val, map, keysSorted);
      if (next !== val) el.setAttribute(attr, next);
    });
  }

  function walkTextNodes(root, map, keysSorted) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node.nodeValue || !normalize(node.nodeValue)) {
          return NodeFilter.FILTER_REJECT;
        }
        if (shouldSkipNode(node)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    var node;
    while ((node = walker.nextNode())) {
      var next = translateText(node.nodeValue, map, keysSorted);
      if (next !== node.nodeValue) {
        node.nodeValue = next;
      }
    }

    root.querySelectorAll('*').forEach(function (el) {
      if (el.hasAttribute('data-i18n-skip')) return;
      translateAttributes(el, map, keysSorted);
    });
  }

  window.BPM.applyTranslations = function (lang) {
    lang = lang || currentLang();
    if (lang === 'ru') {
      document.documentElement.classList.add('i18n-ready');
      document.documentElement.removeAttribute('data-i18n-pending');
      return;
    }

    var bundle = window.BPM_TRANSLATIONS;
    var map = getMap(lang);
    if (!map) {
      document.documentElement.classList.add('i18n-ready');
      return;
    }

    var root = document.getElementById('bpmMain') || document.body;
    walkTextNodes(root, map, bundle.keysSorted);

    var loginRoot = document.querySelector('.auth-page');
    if (loginRoot) walkTextNodes(loginRoot, map, bundle.keysSorted);

    if (document.title) {
      document.title = translateText(document.title, map, bundle.keysSorted);
    }

    document.documentElement.lang = lang;
    document.documentElement.classList.add('i18n-ready');
    document.documentElement.removeAttribute('data-i18n-pending');
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

  function boot() {
    var lang = currentLang();
    if (lang !== 'ru') {
      document.documentElement.setAttribute('data-i18n-pending', '1');
    }
    window.BPM.applyTranslations(lang);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);
