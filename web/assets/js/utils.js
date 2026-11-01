/* ============================================================
   前端通用工具：状态映射、格式化、空/加载态辅助
   ============================================================ */
(function (global) {
  'use strict';

  var LEVEL_NAMES = {
    CONSTITUTION: '宪法',
    LAW: '法律',
    ADMIN_REG: '行政法规',
    LOCAL_REG: '地方性法规',
    DEPT_RULE: '部门规章',
    LOCAL_RULE: '地方政府规章',
    NORMATIVE: '规范性文件',
    OTHER: '其他'
  };

  var VALIDITY_NAMES = {
    DRAFT: '草案',
    EFFECTIVE: '现行有效',
    FUTURE: '尚未生效',
    AMENDED: '已修订',
    ABOLISHED: '已废止',
    EXPIRED: '已失效'
  };

  var INSTITUTION_NAMES = {
    NATIONAL: '国家级',
    PROVINCE: '省级',
    CITY: '市级',
    DISTRICT: '区县级',
    OTHER: '其他'
  };

  var DOC_STATUS_NAMES = {
    PENDING: '待解析',
    PARSING: '解析中',
    PARSED: '已解析',
    INDEXED: '已入库',
    FAILED: '解析失败',
    REVIEWING: '待复核',
    REJECTED: '已驳回'
  };

  var CRAWL_STATUS_NAMES = {
    IDLE: '空闲',
    RUNNING: '采集中',
    SUCCESS: '成功',
    FAILED: '失败',
    NEW: '新发现',
    UPDATED: '有更新',
    UNCHANGED: '无变化'
  };

  // 人工复核状态（ReviewItem）
  var REVIEW_STATUS_NAMES = {
    AUTO: '自动生成',
    PENDING: '待复核',
    APPROVED: '已确认',
    REJECTED: '已驳回'
  };

  // 冲突检测任务状态（ConflictTask）
  var TASK_STATUS_NAMES = {
    PENDING: '排队中',
    RUNNING: '进行中',
    SUCCESS: '已完成',
    FAILED: '失败'
  };

  function reviewStatusClass(status) {
    if (status === 'APPROVED') return 'green';
    if (status === 'REJECTED') return 'red';
    if (status === 'PENDING') return 'orange';
    return 'gray';
  }

  function nameOf(map, value) {
    return map[value] || value || '—';
  }

  function validityClass(status) {
    if (status === 'EFFECTIVE') return 'green';
    if (status === 'FUTURE') return '';
    if (status === 'ABOLISHED' || status === 'EXPIRED') return 'red';
    return 'orange';
  }

  function crawlStatusClass(status) {
    if (status === 'NEW' || status === 'UPDATED') return 'green';
    if (status === 'FAILED') return 'red';
    if (status === 'RUNNING') return '';
    return 'gray';
  }

  function taskStatusClass(status) {
    if (status === 'SUCCESS') return 'green';
    if (status === 'FAILED') return 'red';
    if (status === 'RUNNING') return '';
    return 'gray';
  }

  function truncate(text, limit) {
    if (!text) return '';
    var value = String(text).replace(/\s+/g, ' ').trim();
    return value.length > limit ? value.slice(0, limit) + '…' : value;
  }

  function today() {
    var now = new Date();
    var month = String(now.getMonth() + 1).padStart(2, '0');
    var day = String(now.getDate()).padStart(2, '0');
    return now.getFullYear() + '-' + month + '-' + day;
  }

  /** 生成简易会话号，用于问答上下文分组 */
  function sessionId() {
    if (!global.sessionStorage) return 'web-' + Date.now();
    var cached = global.sessionStorage.getItem('pkb-session');
    if (!cached) {
      cached = 'web-' + Math.random().toString(36).slice(2, 10);
      global.sessionStorage.setItem('pkb-session', cached);
    }
    return cached;
  }

  global.utils = {
    LEVEL_NAMES: LEVEL_NAMES,
    VALIDITY_NAMES: VALIDITY_NAMES,
    INSTITUTION_NAMES: INSTITUTION_NAMES,
    DOC_STATUS_NAMES: DOC_STATUS_NAMES,
    CRAWL_STATUS_NAMES: CRAWL_STATUS_NAMES,
    REVIEW_STATUS_NAMES: REVIEW_STATUS_NAMES,
    TASK_STATUS_NAMES: TASK_STATUS_NAMES,
    nameOf: nameOf,
    validityClass: validityClass,
    crawlStatusClass: crawlStatusClass,
    taskStatusClass: taskStatusClass,
    reviewStatusClass: reviewStatusClass,
    truncate: truncate,
    today: today,
    sessionId: sessionId
  };
})(window);
