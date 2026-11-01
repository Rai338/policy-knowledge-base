/* ============================================================
   接口层：接口地址与请求封装（常量集中管理）
   所有页面统一通过 api.get / api.post 调用，统一处理失败提示
   ============================================================ */
(function (global) {
  'use strict';

  // 接口地址：默认同源；双击本地文件(file://)打开时回退到本机后端，保证也能取数
  // 仍可用 window.PKB_API_BASE 覆盖（例如部署到独立域名时）
  var API_BASE = global.PKB_API_BASE;
  if (!API_BASE) {
    API_BASE = (global.location && global.location.protocol === 'file:')
      ? 'http://127.0.0.1:8000/api'
      : '/api';
  }

  // Element Plus 的 UMD 构建只暴露 ElementPlus 命名空间，页面里习惯用全局 ElMessage。
  // 这里统一补齐（并提供空实现兜底），避免 global.ElMessage 未定义时抛错中断业务流程。
  (function ensureElementPlusGlobals() {
    var names = ['ElMessage', 'ElMessageBox', 'ElNotification', 'ElLoading'];
    names.forEach(function (name) {
      if (!global[name] && global.ElementPlus && global.ElementPlus[name]) {
        global[name] = global.ElementPlus[name];
      }
    });
    if (!global.ElMessage) {
      var noop = function () {};
      var fallback = { success: noop, error: noop, warning: noop, info: noop, closeAll: noop };
      global.ElMessage = new Proxy(fallback, {
        get: function (target, prop) { return target[prop] || noop; }
      });
    }
  })();

  // 登录令牌：持久化在 localStorage，后续请求自动携带（管理端接口需要）
  var TOKEN_KEY = 'pkb_token';
  var authToken = '';
  try {
    authToken = (global.localStorage && global.localStorage.getItem(TOKEN_KEY)) || '';
  } catch (e) { authToken = ''; }

  function isAuthError(payload) {
    var message = (payload && payload.message) || '';
    return payload && payload.code !== 0 && /登录|权限/.test(message);
  }

  function joinParams(url, params) {
    var query = [];
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value === null || value === undefined || value === '') return;
      if (Array.isArray(value)) {
        value.forEach(function (item) { query.push(key + '=' + encodeURIComponent(item)); });
      } else {
        query.push(key + '=' + encodeURIComponent(value));
      }
    });
    if (!query.length) return url;
    return url + (url.indexOf('?') >= 0 ? '&' : '?') + query.join('&');
  }

  function notifyError(message) {
    if (global.ElMessage) {
      global.ElMessage.error(message || '请求失败，请稍后重试');
    } else if (global.console) {
      console.error(message);
    }
  }

  /**
   * 统一请求：业务 code!==0 视为失败，自动提示
   * @param {string} url 相对接口路径，如 /documents
   * @param {object} options {method, params, body, silent}
   */
  function request(url, options) {
    options = options || {};
    var method = (options.method || 'GET').toUpperCase();
    var target = API_BASE + url;
    if (method === 'GET' && options.params) {
      target = joinParams(target, options.params);
    }
    var init = { method: method, headers: {} };
    if (authToken) {
      init.headers['Authorization'] = 'Bearer ' + authToken;
    }
    if (options.body) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(options.body);
    }
    return fetch(target, init)
      .then(function (response) {
        if (response.ok) {
          return response.json();
        }
        // 非 2xx：尽量解析后端业务报文（如 401「用户名或密码不正确」），提示才准确
        return response
          .json()
          .catch(function () { return null; })
          .then(function (payload) {
            var message = (payload && payload.message) || ('HTTP ' + response.status + ' ' + target);
            // 404 且请求的是本系统接口：多半是浏览器缓存了旧版页面（旧脚本调用了已变更的接口），
            // 直接给出可操作的指引，避免用户只能看到干巴巴的状态码。
            if (response.status === 404) {
              message = '接口不存在（' + target + '），可能是页面缓存过期，请按 Ctrl + F5 强制刷新后重试';
            }
            var error = new Error(message);
            error.httpStatus = response.status;
            throw error;
          });
      })
      .then(function (payload) {
        if (!payload || payload.code !== 0) {
          var message = (payload && payload.message) || '请求失败';
          // 令牌失效/无权限：清理本地令牌，交由外壳重新进入登录页
          if (isAuthError(payload)) {
            api.setToken('');
            if (global.appAuth) global.appAuth.clear && global.appAuth.clear();
          }
          if (!options.silent) notifyError(message);
          var bizError = new Error(message);
          bizError.notified = true;
          throw bizError;
        }
        return payload.data;
      })
      .catch(function (error) {
        if (!options.silent && error && !error.notified) {
          // HTTP 状态错误：直接展示后端报文（如 401 用户名或密码不正确）
          if (error.httpStatus) {
            notifyError(error.message);
          } else {
            notifyError('服务连接失败（' + (error.message || '网络异常') + '），请确认后端已启动');
          }
        }
        throw error;
      });
  }

  function upload(url, formData) {
    var headers = authToken ? { Authorization: 'Bearer ' + authToken } : {};
    return fetch(API_BASE + url, { method: 'POST', body: formData, headers: headers })
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (!payload || payload.code !== 0) {
          var message = (payload && payload.message) || '上传失败';
          notifyError(message);
          throw new Error(message);
        }
        return payload.data;
      });
  }

  var api = {
    API_BASE: API_BASE,
    request: request,
    upload: upload,
    // 登录令牌读写（登录/登出时由外壳调用）
    getToken: function () { return authToken; },
    setToken: function (token) {
      authToken = token || '';
      try {
        if (authToken) {
          global.localStorage.setItem(TOKEN_KEY, authToken);
        } else {
          global.localStorage.removeItem(TOKEN_KEY);
        }
      } catch (e) { /* 隐私模式等场景下忽略 */ }
    },
    get: function (url, params, options) {
      return request(url, Object.assign({}, options, { method: 'GET', params: params }));
    },
    post: function (url, body, options) {
      return request(url, Object.assign({}, options, { method: 'POST', body: body || {} }));
    },
    put: function (url, body, options) {
      return request(url, Object.assign({}, options, { method: 'PUT', body: body || {} }));
    },
    del: function (url, options) {
      return request(url, Object.assign({}, options, { method: 'DELETE' }));
    }
  };

  // ---------------- 各业务接口（集中维护路径，页面不写死 URL）----------------
  api.documents = {
    list: function (params) { return api.get('/documents', params); },
    detail: function (id, params) { return api.get('/documents/' + id, params); },
    upload: function (formData) { return api.upload('/documents/upload', formData); },
    importText: function (body) { return api.post('/documents/text', body); },
    importSamples: function () { return api.post('/documents/import-samples', {}); },
    remove: function (id) { return api.del('/documents/' + id); },
    reindex: function (id) { return api.post('/documents/' + id + '/reindex', {}); },
    review: function (id, body) { return api.post('/documents/' + id + '/review', body); },
    blocks: function (id, params) { return api.get('/documents/' + id + '/blocks', params); }
  };

  api.search = {
    query: function (params) { return api.get('/search', params); },
    suggest: function (keyword) { return api.get('/search/suggest', { q: keyword }); },
    block: function (blockId) { return api.get('/blocks/' + blockId); },
    similar: function (blockId, topK) { return api.get('/blocks/' + blockId + '/similar', { top_k: topK || 5 }); }
  };

  api.qa = {
    ask: function (body) { return api.post('/qa/ask', body); },
    feedback: function (body) { return api.post('/qa/feedback', body); },
    history: function (params) { return api.get('/qa/history', params); }
  };

  api.analysis = {
    summary: function (documentId) { return api.get('/analysis/summary/' + documentId); },
    interpret: function (documentId) { return api.get('/analysis/interpret/' + documentId); },
    term: function (term) { return api.post('/analysis/term', { term: term }); },
    related: function (params) { return api.get('/analysis/related', params); },
    compare: function (documentId) { return api.get('/analysis/compare/' + documentId); },
    applicability: function (body) { return api.post('/analysis/applicability', body); }
  };

  api.conflict = {
    dimensions: function () { return api.get('/conflict/dimensions'); },
    create: function (body) { return api.post('/conflict/tasks', body); },
    list: function (params) { return api.get('/conflict/tasks', params); },
    get: function (taskId, options) { return api.get('/conflict/tasks/' + taskId, null, options); },
    exportReport: function (taskId) { return api.post('/conflict/tasks/' + taskId + '/export', {}); },
    downloadUrl: function (taskId) { return API_BASE + '/conflict/tasks/' + taskId + '/download'; }
  };

  api.crawl = {
    sources: function (params) { return api.get('/crawl/sources', params); },
    test: function (body) { return api.post('/crawl/sources/test', body); },
    createSource: function (body) { return api.post('/crawl/sources', body); },
    updateSource: function (id, body) { return api.put('/crawl/sources/' + id, body); },
    removeSource: function (id) { return api.del('/crawl/sources/' + id); },
    runSource: function (id) { return api.post('/crawl/sources/' + id + '/run', {}); },
    runAll: function () { return api.post('/crawl/run-all', {}); },
    records: function (params) { return api.get('/crawl/records', params); },
    stats: function () { return api.get('/crawl/stats'); },
    jobs: function () { return api.get('/crawl/jobs'); },
    sync: function () { return api.post('/crawl/sync', {}); }
  };

  api.admin = {
    options: function () { return api.get('/admin/dict/options'); },
    dictList: function (params) { return api.get('/admin/dict', params); },
    createDict: function (body) { return api.post('/admin/dict', body); },
    updateDict: function (id, body) { return api.put('/admin/dict/' + id, body); },
    removeDict: function (id) { return api.del('/admin/dict/' + id); },
    reviewQueue: function (params) { return api.get('/admin/review', params); },
    reviewDetail: function (id) { return api.get('/admin/review/' + id); },
    handleReview: function (id, body) { return api.post('/admin/review/' + id, body); },
    reindex: function () { return api.post('/admin/reindex', {}); },
    overview: function () { return api.get('/admin/overview'); },
    todo: function () { return api.get('/admin/todo'); },
    // 政策法规后台增删改查（管理员）
    docList: function (params) { return api.get('/admin/documents', params); },
    createDoc: function (body) { return api.post('/admin/documents', body); },
    updateDoc: function (id, body) { return api.put('/admin/documents/' + id, body); },
    removeDoc: function (id) { return api.del('/admin/documents/' + id); },
    users: {
      list: function () { return api.get('/admin/users'); },
      create: function (body) { return api.post('/admin/users', body); },
      update: function (id, body) { return api.put('/admin/users/' + id, body); },
      remove: function (id) { return api.del('/admin/users/' + id); }
    }
  };

  api.auth = {
    login: function (body) { return api.post('/auth/login', body); },
    register: function (body) { return api.post('/auth/register', body); },
    me: function (options) { return api.get('/auth/me', null, options); },
    roles: function () { return api.get('/auth/roles'); }
  };

  api.logs = {
    operations: function (params) { return api.get('/logs/operations', params); },
    search: function (params) { return api.get('/logs/search', params); },
    qa: function (params) { return api.get('/logs/qa', params); },
    summary: function () { return api.get('/logs/summary'); }
  };

  api.dashboard = {
    stats: function (options) { return api.get('/dashboard/stats', null, options); },
    trend: function (days) { return api.get('/dashboard/trend', { days: days || 7 }); }
  };

  api.meta = {
    theme: function () { return api.get('/meta/theme'); },
    options: function () { return api.get('/meta/options'); },
    regions: function () { return api.get('/meta/regions'); }
  };

  global.api = api;
})(window);
