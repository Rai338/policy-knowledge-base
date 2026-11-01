/* ============================================================
   应用外壳：侧栏、顶栏、Hash 路由、移动端菜单、主题注入
   视觉语言与 policy-workbench 原型一致：
     · 左侧固定面板 = 品牌 + 当前范围 + 导航 + 数据更新于 / 用户菜单
     · 顶栏 = 当前页面标题 + 数据集与库规模
     · 导航结构对齐项目书 8.4（工作台 / 政策搜索 / 解读与关联 / 数据总览 + 管理）
   ============================================================ */
(function (global) {
  'use strict';

  // 导航图标：线性风格，颜色跟随导航项状态（currentColor）
  var ICONS = {
    dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.6"/></svg>',
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 15a3 3 0 0 1-3 3H8l-4 3V6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3z"/><path d="M8 9h8M8 12.5h5"/></svg>',
    library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H9a2 2 0 0 1 2 2v13a1.5 1.5 0 0 0-1.5-1.5H4z"/><path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H15a2 2 0 0 0-2 2v13a1.5 1.5 0 0 1 1.5-1.5H20z"/></svg>',
    link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a4 4 0 0 0 5.7.4l2.6-2.6a4 4 0 0 0-5.7-5.7L11.4 6.3"/><path d="M14 11a4 4 0 0 0-5.7-.4l-2.6 2.6a4 4 0 0 0 5.7 5.7l1.2-1.2"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16"/><path d="M7 20V11M12 20V5M17 20v-6"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6z"/><path d="M12 9v4M12 16h.01"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>',
    tag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 13.5L13 21a2 2 0 0 1-2.8 0l-6.7-6.7A2 2 0 0 1 3 12.9V5a2 2 0 0 1 2-2h7.9a2 2 0 0 1 1.4.6l6.2 6.2a2 2 0 0 1 0 2.7z"/><circle cx="8" cy="8" r="1.4"/></svg>',
    cloud: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 18H7a4 4 0 0 1-.6-7.9A5.5 5.5 0 0 1 17 9.5a4.2 4.2 0 0 1 .5 8.5z"/><path d="M12 12v5M9.5 14.5L12 17l2.5-2.5"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 8l-4 4 4 4M6 12h9"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="3.5"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/></svg>'
  };

  // 导航配置：adminOnly 的分组仅管理员可见，普通用户保持简洁。
  // 名称与分组对齐项目书 8.4「工作台 / 政策搜索 / 解读与关联 / 数据总览 + 管理」。
  var NAV_GROUPS = [
    {
      title: '',
      items: [
        { name: 'home', label: '工作台', view: 'home', icon: ICONS.dashboard },
        { name: 'documents', label: '政策搜索', view: 'documents', icon: ICONS.search },
        { name: 'analysis', label: '解读与关联', view: 'analysis', icon: ICONS.link },
        { name: 'overview', label: '数据总览', view: 'overview', icon: ICONS.chart }
      ]
    },
    {
      title: '管理',
      adminOnly: true,
      items: [
        { name: 'manage', label: '政策文件', view: 'manage', icon: ICONS.file },
        { name: 'crawl', label: '采集源', view: 'crawl', icon: ICONS.cloud },
        { name: 'admin', label: '字典与复核', view: 'admin', icon: ICONS.tag },
        { name: 'conflict', label: '冲突初筛', view: 'conflict', icon: ICONS.shield },
        { name: 'logs', label: '日志审计', view: 'logs', icon: ICONS.clock },
        { name: 'users', label: '账号管理', view: 'users', icon: ICONS.user }
      ]
    }
  ];

  function parseHash() {
    var raw = (global.location.hash || '#/home').replace(/^#\/?/, '');
    var parts = raw.split('?');
    var name = parts[0] || 'home';
    var query = {};
    if (parts[1]) {
      parts[1].split('&').forEach(function (pair) {
        if (!pair) return;
        var kv = pair.split('=');
        query[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || '');
      });
    }
    return { name: name, query: query };
  }

  var router = {
    state: null,
    go: function (name, query) {
      var target = '#/' + name;
      if (query) {
        var pairs = Object.keys(query).filter(function (key) {
          return query[key] !== undefined && query[key] !== null && query[key] !== '';
        }).map(function (key) {
          return encodeURIComponent(key) + '=' + encodeURIComponent(query[key]);
        });
        if (pairs.length) target += '?' + pairs.join('&');
      }
      global.location.hash = target;
    },
    getQuery: function (key) {
      var parsed = parseHash();
      return parsed.query[key] || '';
    },
    parse: parseHash
  };

  global.appRouter = router;

  // ---------------------------------------------------------------- 登录态
  // 令牌由 api.js 持久化在 localStorage；此处保存当前用户，供角色导航与展示使用。
  var authState = global.Vue.reactive({ user: null });

  // 地区切换全局状态（A+C 方案）：选中某市后，检索 / 问答 / 冲突初筛均按
  // 「本市 → 本省（仅省） → 全国」梯度召回。选择持久化在 localStorage，
  // 并通过自定义事件通知各页面刷新数据。
  var regionState = global.Vue.reactive({
    value: (function () {
      try { return global.localStorage.getItem('pkb_region') || ''; } catch (e) { return ''; }
    })()
  });
  global.appRegion = {
    state: regionState,
    get: function () { return regionState.value; },
    set: function (region) {
      regionState.value = region || '';
      try { global.localStorage.setItem('pkb_region', regionState.value); } catch (e) { /* ignore */ }
      try { global.dispatchEvent(new CustomEvent('pkb:region-change', { detail: regionState.value })); } catch (e) { /* ignore */ }
    },
    name: function () {
      var r = regionState.value;
      if (!r) return '全国（全部）';
      for (var i = 0; i < (global.__pkbRegions || []).length; i++) {
        if (global.__pkbRegions[i].code === r) return global.__pkbRegions[i].name;
      }
      return r;
    },
    // 顶栏「XX政策数据集」用的短名
    short: function () {
      var r = regionState.value;
      if (!r) return '全国';
      var full = global.appRegion.name();
      return full.replace(/（.*?）$/, '');
    }
  };

  global.appAuth = {
    state: authState,
    isAdmin: function () {
      return !!(authState.user && authState.user.role === 'ADMIN');
    },
    apply: function (user, token) {
      authState.user = user || null;
      if (token) {
        global.api.setToken(token);
      }
    },
    clear: function () {
      authState.user = null;
      global.api.setToken('');
    },
    logout: function () {
      global.appAuth.clear();
      router.go('home');
    }
  };

  var App = {
    template: [
      '<div>',
      '  <view-login v-if="!authed" @logged-in="onLoggedIn" />',
      '  <div class="app-shell" v-else>',
      '    <aside class="app-sidebar" :class="{ open: menuOpen }">',
      '      <div class="brand">',
      '        <div class="brand-logo">政</div>',
      '        <div>',
      '          <div class="brand-title">{{ appName }}</div>',
      '          <div class="brand-sub">POLICY KNOWLEDGE BASE</div>',
      '        </div>',
      '      </div>',
      '',
      '      <div class="scope-box">',
      '        <div class="scope-label">当前范围</div>',
      '        <el-select v-model="region" class="scope-select" size="small"',
      '          placeholder="全国（全部）"',
      '          title="地区切换：选中某市后按本市→本省→全国梯度召回">',
      '          <el-option v-for="r in regions" :key="r.code" :label="r.name" :value="r.code" />',
      '        </el-select>',
      '      </div>',
      '',
      '      <div class="nav-list">',
      '        <div v-for="group in navGroups" :key="group.title || \'_primary\'">',
      '          <div v-if="group.title" class="nav-group-title">{{ group.title }}</div>',
      '          <div v-for="item in group.items" :key="item.name" class="nav-item"',
      '            :class="{ active: current === item.name }" :title="item.label"',
      '            @click="navigate(item.name)">',
      '            <span class="nav-icon" v-html="item.icon"></span>',
      '            <span class="nav-label">{{ item.label }}</span>',
      '          </div>',
      '        </div>',
      '      </div>',
      '',
      '      <div class="sidebar-foot">',
      '        <div class="updated">数据更新于 {{ today }}</div>',
      '        <button class="user-trigger" @click="userMenuOpen = !userMenuOpen">',
      '          <span class="user-avatar">{{ userInitial }}</span>',
      '          <span class="user-info">',
      '            <span class="user-name">{{ userName }}</span>',
      '            <span class="user-role">{{ userRoleName }}</span>',
      '          </span>',
      '        </button>',
      '        <div v-if="userMenuOpen" class="user-menu">',
      '          <button class="user-menu-item" @click="navigate(\'overview\')">',
      '            <span class="nav-icon" v-html="icons.user"></span>数据总览',
      '          </button>',
      '          <div class="user-menu-sep"></div>',
      '          <button class="user-menu-item danger" @click="logout">',
      '            <span class="nav-icon" v-html="icons.logout"></span>退出登录',
      '          </button>',
      '        </div>',
      '      </div>',
      '    </aside>',
      '    <div v-if="menuOpen" class="sidebar-mask" @click="menuOpen = false"></div>',
      '',
      '    <div class="app-main">',
      '      <header class="app-header">',
      '        <div class="header-left">',
      '          <el-button class="mobile-only" size="small" @click="menuOpen = !menuOpen">菜单</el-button>',
      '          <div class="h2">{{ currentLabel }}</div>',
      '        </div>',
      '        <div class="header-right">',
      '          <div class="header-meta">{{ datasetLabel }}</div>',
      '        </div>',
      '      </header>',
      '      <main class="app-content">',
      '        <component :is="currentView" :key="viewKey" />',
      '      </main>',
      '    </div>',
      '  </div>',
      '</div>'
    ].join(''),

    setup: function () {
      var Vue = global.Vue;
      var refs = Vue.reactive({
        current: 'home',
        query: {},
        menuOpen: false,
        userMenuOpen: false,
        appName: '政策知识库',
        version: '0.1.0',
        renderKey: 0,
        regions: [],
        stats: {},
        today: new Date().toISOString().slice(0, 10)
      });

      var viewMap = {};
      NAV_GROUPS.forEach(function (group) {
        group.items.forEach(function (item) {
          // adminOnly 标记在分组上，需下沉到条目，供路由/标题的越权判断使用
          item.adminOnly = item.adminOnly || !!group.adminOnly;
          viewMap[item.name] = item;
        });
      });

      function syncFromHash() {
        var parsed = parseHash();
        if (!viewMap[parsed.name]) parsed.name = 'home';
        refs.current = parsed.name;
        refs.query = parsed.query;
        refs.renderKey += 1;
        refs.menuOpen = false;
        refs.userMenuOpen = false;
      }

      // 刷新页面后若本地仍有令牌，向后端换取当前用户，保持登录态
      function restoreSession() {
        if (!global.api.getToken()) {
          return;
        }
        global.api.auth.me({ silent: true }).then(function (data) {
          global.appAuth.apply(data && data.user);
        }).catch(function () {
          global.appAuth.clear();
        });
      }

      Vue.onMounted(function () {
        global.addEventListener('hashchange', syncFromHash);
        syncFromHash();
        restoreSession();
        global.api.dashboard.stats({ silent: true }).then(function (data) {
          refs.stats = data || {};
        }).catch(function () {});
        global.api.meta.theme().then(function (data) {
          // 版本自检：浏览器若仍在使用缓存的旧页面，会自动带时间戳重载一次（自愈），
          // 避免"服务端已更新、页面却停留在旧版"（甚至旧脚本请求到已变更接口而报 404）。
          if (data && data.app && data.app.build && global.PKB_BUILD
              && data.app.build !== global.PKB_BUILD) {
            try {
              if (global.sessionStorage.getItem('pkb_build_done') !== data.app.build) {
                global.sessionStorage.setItem('pkb_build_done', data.app.build);
                global.location.replace(global.location.pathname + '?t=' + Date.now());
                return;
              }
            } catch (e) { /* 隐私模式等场景下无法写 sessionStorage，忽略即可 */ }
          }
          if (data && data.app) {
            refs.appName = data.app.name || refs.appName;
            refs.version = data.app.version || refs.version;
          }
          if (data && data.vars) {
            var root = document.documentElement;
            Object.keys(data.vars).forEach(function (key) {
              root.style.setProperty('--color-' + kebab(key), data.vars[key]);
            });
          }
        }).catch(function () {});
        global.api.meta.regions().then(function (data) {
          refs.regions = data || [];
          global.__pkbRegions = refs.regions;
          // 校正持久化的地域值是否仍在可选范围内
          var codes = refs.regions.map(function (r) { return r.code; });
          if (refs.regions.length && codes.indexOf(global.appRegion.get()) < 0) {
            global.appRegion.set('');
          }
        }).catch(function () {});
      });

      function kebab(value) {
        return value.replace(/([A-Z])/g, '-$1').toLowerCase();
      }

      return {
        // 导航按角色过滤：管理员可见全部，普通用户只看到简洁的知识服务
        navGroups: Vue.computed(function () {
          var isAdmin = global.appAuth.isAdmin();
          return NAV_GROUPS.filter(function (group) {
            return !group.adminOnly || isAdmin;
          });
        }),
        icons: ICONS,
        authed: Vue.computed(function () { return !!(authState.user); }),
        userInitial: Vue.computed(function () {
          var user = authState.user;
          var name = user ? (user.display_name || user.username || '') : '';
          return name ? name.slice(0, 1) : '?';
        }),
        userName: Vue.computed(function () {
          return authState.user ? (authState.user.display_name || authState.user.username) : '';
        }),
        userRoleName: Vue.computed(function () {
          return authState.user ? (authState.user.role_name || authState.user.role) : '';
        }),
        today: Vue.computed(function () { return refs.today; }),
        onLoggedIn: function (payload) {
          global.appAuth.apply(payload && payload.user, payload && payload.token);
          router.go('home');
        },
        logout: function () {
          global.appAuth.logout();
        },
        current: Vue.computed(function () { return refs.current; }),
        menuOpen: Vue.computed({
          get: function () { return refs.menuOpen; },
          set: function (value) { refs.menuOpen = value; }
        }),
        userMenuOpen: Vue.computed({
          get: function () { return refs.userMenuOpen; },
          set: function (value) { refs.userMenuOpen = value; }
        }),
        appName: Vue.computed(function () { return refs.appName; }),
        version: Vue.computed(function () { return refs.version; }),
        region: Vue.computed({
          get: function () { return global.appRegion.state.value; },
          set: function (value) { global.appRegion.set(value); }
        }),
        regions: Vue.computed(function () { return refs.regions; }),
        apiBase: Vue.computed(function () { return global.api.API_BASE; }),
        // 顶栏右侧：当前地区 + 库规模（原型中为「XX 数据集」标签位）
        datasetLabel: Vue.computed(function () {
          var docs = refs.stats.documents;
          var blocks = refs.stats.blocks;
          var head = global.appRegion.short() + '政策数据集';
          if (!docs) return head;
          return head + ' · ' + docs + ' 份文件 / ' + blocks + ' 个知识块';
        }),
        currentLabel: Vue.computed(function () {
          var item = viewMap[refs.current];
          if (item && item.adminOnly && !global.appAuth.isAdmin()) {
            return '工作台';
          }
          return item ? item.label : '工作台';
        }),
        currentView: Vue.computed(function () {
          var item = viewMap[refs.current];
          // 越权保护：非管理员直接访问管理端路由时回退首页（后端另有权限校验）
          if (item && item.adminOnly && !global.appAuth.isAdmin()) {
            return global.views.home;
          }
          return (global.views && item && global.views[item.view]) || global.views.home;
        }),
        viewKey: Vue.computed(function () {
          return refs.current + '-' + refs.renderKey + '-' + JSON.stringify(refs.query);
        }),
        navigate: function (name) {
          router.go(name);
        }
      };
    }
  };

  function bootstrap() {
    var Vue = global.Vue;
    var app = Vue.createApp(App);
    app.use(global.ElementPlus, { locale: global.ElementPlusLocaleZhCn });
    Object.keys(global.views || {}).forEach(function (name) {
      app.component('view-' + name, global.views[name]);
    });
    // 让 <component :is="..."> 直接使用组件对象
    app.config.globalProperties.$views = global.views;
    app.mount('#app');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
})(window);
